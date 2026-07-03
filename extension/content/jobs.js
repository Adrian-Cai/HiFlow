(function () {
  'use strict';

  const MAX_SCAN_COUNT = 8;
  const lastScannedCards = new Map();

  function makeJobId(jobMeta = {}) {
    return [
      jobMeta.company || '',
      jobMeta.title || '',
      jobMeta.salary || '',
      jobMeta.location || '',
      jobMeta.link || ''
    ].join('|');
  }

  function makeJobPayload(cardMeta, snapshot) {
    const payload = {
      cardMeta,
      snapshot,
      jobText: snapshot?.text || '',
      jobMeta: {
        title: snapshot?.title || cardMeta?.title || '',
        company: snapshot?.company || cardMeta?.company || '',
        salary: snapshot?.salary || cardMeta?.salary || '',
        location: snapshot?.location || cardMeta?.location || '',
        link: cardMeta?.link || snapshot?.url || location.href
      }
    };

    payload.id = makeJobId(payload.jobMeta);
    return payload;
  }

  async function collectCurrentJob() {
    const snapshot = window.HiFlowDom.getCurrentJobSnapshot();
    return {
      ok: Boolean(snapshot.text && snapshot.text.length >= 80),
      page: 'jobs',
      job: makeJobPayload({}, snapshot)
    };
  }

  async function scanVisibleJobs(limit = MAX_SCAN_COUNT) {
    const cards = window.HiFlowDom.getCurrentVisibleJobCards(limit);
    const jobs = [];
    const skipped = [];

    for (let i = 0; i < cards.length; i++) {
      const card = cards[i];
      const cardMeta = window.HiFlowDom.extractJobCardMeta(card);

      chrome.runtime.sendMessage({
        type: 'HIFLOW_SCAN_PROGRESS',
        payload: {
          index: i + 1,
          total: cards.length,
          title: cardMeta.title || '未识别岗位'
        }
      }).catch(() => {});

      card.scrollIntoView({ block: 'center', behavior: 'smooth' });
      await window.HiFlowDom.sleep(350);
      card.click();

      const waitResult = await window.HiFlowDom.waitRightDetailReadyForCard(cardMeta, 7000);
      if (!waitResult.ok) {
        skipped.push({
          reason: 'DETAIL_NOT_SYNCED',
          cardMeta,
          snapshot: waitResult.snapshot
        });
        continue;
      }

      if (!waitResult.snapshot.text || waitResult.snapshot.text.length < 80) {
        skipped.push({
          reason: 'DETAIL_EMPTY',
          cardMeta,
          snapshot: waitResult.snapshot
        });
        continue;
      }

      const job = makeJobPayload(cardMeta, waitResult.snapshot);
      jobs.push(job);
      lastScannedCards.set(job.id, { card, cardMeta });
      await window.HiFlowDom.sleep(700);
    }

    return {
      ok: true,
      page: 'jobs',
      jobs,
      skipped,
      scannedAt: new Date().toISOString()
    };
  }

  function findCardForJob(job) {
    if (lastScannedCards.has(job.id)) {
      return lastScannedCards.get(job.id);
    }

    const cards = window.HiFlowDom.getCurrentVisibleJobCards(MAX_SCAN_COUNT);
    for (const card of cards) {
      const cardMeta = window.HiFlowDom.extractJobCardMeta(card);
      const payload = makeJobPayload(cardMeta, {});
      if (payload.id === job.id || makeJobId(job.jobMeta || {}) === makeJobId(payload.jobMeta)) {
        return { card, cardMeta };
      }
    }

    return null;
  }

  function findClickableByText(texts) {
    const candidates = Array.from(document.querySelectorAll('button, a, div, span'))
      .filter(el => {
        const text = (el.innerText || el.textContent || '').trim();
        if (!text || text.length > 30) return false;
        return texts.some(keyword => text.includes(keyword));
      });

    for (const candidate of candidates) {
      const clickable = candidate.closest('button, a, [role="button"]') || candidate;
      const rect = clickable.getBoundingClientRect();
      const style = window.getComputedStyle(clickable);
      if (rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden') {
        return clickable;
      }
    }

    return null;
  }

  function findGreetingInput() {
    const selectors = [
      'textarea',
      'input[type="text"]',
      '[contenteditable="true"]',
      '.chat-input textarea',
      '.input-area textarea',
      '[class*="input"] textarea',
      '[class*="editor"]'
    ];

    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (!el) continue;
      const rect = el.getBoundingClientRect();
      const style = window.getComputedStyle(el);
      if (rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden') {
        return el;
      }
    }

    return null;
  }

  function fillInput(input, text) {
    input.focus();

    if ('value' in input) {
      input.value = text;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
      return;
    }

    input.innerText = text;
    input.dispatchEvent(new InputEvent('input', {
      bubbles: true,
      inputType: 'insertText',
      data: text
    }));
  }

  async function prepareGreetingForJobs(jobs = [], options = {}) {
    const actions = [];
    const autoSend = Boolean(options.autoSend);

    for (const job of jobs) {
      const entry = findCardForJob(job);

      if (!entry?.card) {
        actions.push({
          id: job.id,
          status: 'CARD_NOT_FOUND',
          title: job.jobMeta?.title || '',
          message: '没有找到对应岗位卡片'
        });
        continue;
      }

      entry.card.scrollIntoView({ block: 'center', behavior: 'smooth' });
      await window.HiFlowDom.sleep(350);
      entry.card.click();

      const waitResult = await window.HiFlowDom.waitRightDetailReadyForCard(entry.cardMeta, 7000);
      if (!waitResult.ok) {
        actions.push({
          id: job.id,
          status: 'DETAIL_NOT_SYNCED',
          title: job.jobMeta?.title || '',
          message: '右侧详情没有同步到该岗位'
        });
        continue;
      }

      const communicateBtn = findClickableByText(['立即沟通', '继续沟通', '打招呼', '感兴趣', '沟通']);
      if (!communicateBtn) {
        actions.push({
          id: job.id,
          status: 'COMMUNICATE_BUTTON_NOT_FOUND',
          title: job.jobMeta?.title || '',
          message: '没有找到沟通按钮'
        });
        continue;
      }

      communicateBtn.click();
      await window.HiFlowDom.sleep(1000);

      const input = findGreetingInput();
      if (!input) {
        actions.push({
          id: job.id,
          status: 'COMMUNICATE_OPENED_NO_INPUT',
          title: job.jobMeta?.title || '',
          message: '已点击沟通，但没有识别到输入框'
        });
        continue;
      }

      fillInput(input, job.firstMessage || '您好，我对这个岗位比较感兴趣，方便进一步沟通吗？');

      if (autoSend) {
        await window.HiFlowDom.sleep(500);
        const sendBtn = findClickableByText(['发送']);

        if (!sendBtn) {
          actions.push({
            id: job.id,
            status: 'SEND_BUTTON_NOT_FOUND',
            title: job.jobMeta?.title || '',
            message: '已填入话术，但没有找到发送按钮'
          });
          continue;
        }

        sendBtn.click();
        actions.push({
          id: job.id,
          status: 'GREETING_SENT',
          title: job.jobMeta?.title || '',
          message: '已填入并发送第一条打招呼'
        });

        await window.HiFlowDom.sleep(1200);
        continue;
      }

      actions.push({
        id: job.id,
        status: 'GREETING_FILLED',
        title: job.jobMeta?.title || '',
        message: '已打开沟通并填入话术，等待人工确认发送'
      });

      await window.HiFlowDom.sleep(900);
    }

    return { ok: true, actions };
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (!message || !message.type) return false;

    if (message.type === 'HIFLOW_COLLECT_CURRENT_JOB') {
      collectCurrentJob().then(sendResponse).catch(error => {
        sendResponse({ ok: false, error: error.message });
      });
      return true;
    }

    if (message.type === 'HIFLOW_SCAN_VISIBLE_JOBS') {
      scanVisibleJobs(Number(message.limit || MAX_SCAN_COUNT)).then(sendResponse).catch(error => {
        sendResponse({ ok: false, error: error.message });
      });
      return true;
    }

    if (message.type === 'HIFLOW_PREPARE_GREETING_FOR_JOBS') {
      prepareGreetingForJobs(message.jobs || [], { autoSend: message.autoSend }).then(sendResponse).catch(error => {
        sendResponse({ ok: false, error: error.message });
      });
      return true;
    }

    return false;
  });

  chrome.runtime.sendMessage({
    type: 'HIFLOW_PAGE_READY',
    payload: {
      page: 'jobs',
      url: location.href,
      title: document.title
    }
  }).catch(() => {});
})();
