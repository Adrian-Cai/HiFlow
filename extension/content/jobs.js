(function () {
  'use strict';

  const MAX_SCAN_COUNT = 8;
  const lastScannedCards = new Map();
  const CARD_SCORE_STYLE_ID = 'hiflow-job-card-score-style';

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

  function simpleText(value) {
    return String(value || '')
      .replace(/\s+/g, '')
      .replace(/[()（）【】\[\]「」『』<>《》，,.。/\\|·\-_:：;；]/g, '')
      .toLowerCase();
  }

  function doesSnapshotMatchCard(snapshot = {}, cardMeta = {}) {
    const detailText = simpleText(snapshot.text || '');
    const detailTitle = simpleText(snapshot.title || '');
    const detailCompany = simpleText(snapshot.company || '');
    const cardTitle = simpleText(cardMeta.title || '');
    const cardCompany = simpleText(cardMeta.company || '');

    if (!cardTitle) return false;
    if (detailText.includes(cardTitle) || detailTitle.includes(cardTitle) || cardTitle.includes(detailTitle)) return true;
    if (cardTitle.length >= 5 && detailText.includes(cardTitle.slice(0, 5))) return true;
    if (cardTitle.length >= 4 && detailTitle.includes(cardTitle.slice(0, 4))) return true;
    return Boolean(cardCompany && (detailText.includes(cardCompany) || detailCompany.includes(cardCompany)));
  }

  function getCurrentCardEntry(snapshot = {}) {
    const cards = window.HiFlowDom.getCurrentVisibleJobCards(MAX_SCAN_COUNT);
    const activeSelectors = [
      '.job-card-wrapper.active',
      '.job-card-wrapper.selected',
      '.job-card-wrapper.cur',
      '.job-card-body.active',
      '.job-card-body.selected',
      '[class*="job-card"][class*="active"]',
      '[class*="job-card"][class*="selected"]'
    ];

    for (const selector of activeSelectors) {
      const activeCard = document.querySelector(selector);
      if (!activeCard) continue;
      const card = cards.find(item => item === activeCard || item.contains(activeCard) || activeCard.contains(item)) || activeCard;
      const cardMeta = window.HiFlowDom.extractJobCardMeta(card);
      if (doesSnapshotMatchCard(snapshot, cardMeta)) return { card, cardMeta };
    }

    for (const card of cards) {
      const cardMeta = window.HiFlowDom.extractJobCardMeta(card);
      if (doesSnapshotMatchCard(snapshot, cardMeta)) return { card, cardMeta };
    }

    return null;
  }

  async function collectCurrentJob() {
    const snapshot = window.HiFlowDom.getCurrentJobSnapshot();
    const currentEntry = getCurrentCardEntry(snapshot);
    const job = makeJobPayload(currentEntry?.cardMeta || {}, snapshot);

    if (currentEntry?.card) {
      lastScannedCards.set(job.id, currentEntry);
    }

    return {
      ok: Boolean(snapshot.text && snapshot.text.length >= 80),
      page: 'jobs',
      job
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

  function ensureCardScoreStyle() {
    if (document.getElementById(CARD_SCORE_STYLE_ID)) return;

    const style = document.createElement('style');
    style.id = CARD_SCORE_STYLE_ID;
    style.textContent = `
      .hiflow-job-card-scored {
        position: relative !important;
      }
      .hiflow-job-score-badge {
        position: absolute;
        top: 10px;
        right: 12px;
        z-index: 20;
        display: inline-grid;
        grid-template-columns: auto auto;
        align-items: baseline;
        gap: 4px;
        min-width: 76px;
        min-height: 28px;
        padding: 3px 8px 4px;
        border: 1px solid rgba(8, 125, 112, 0.28);
        border-radius: 6px;
        color: #075d58;
        background: rgba(238, 246, 244, 0.96);
        box-shadow: 0 6px 16px rgba(15, 23, 42, 0.10);
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        line-height: 1;
        pointer-events: none;
      }
      .hiflow-job-score-badge strong {
        font-size: 18px;
        font-weight: 900;
        letter-spacing: 0;
      }
      .hiflow-job-score-badge span {
        font-size: 11px;
        font-weight: 760;
        white-space: nowrap;
      }
      .hiflow-job-score-badge.is-warn {
        border-color: rgba(223, 95, 24, 0.30);
        color: #b54708;
        background: rgba(255, 247, 237, 0.96);
      }
      .hiflow-job-score-badge.is-low {
        border-color: rgba(148, 163, 184, 0.36);
        color: #475569;
        background: rgba(248, 250, 252, 0.96);
      }
    `;
    document.head.appendChild(style);
  }

  function getScoreTone(result = {}) {
    const score = Number(result.score || 0);
    if (result.decision === 'RECOMMEND' || score >= 90) return 'ok';
    if (score >= 70) return 'warn';
    return 'low';
  }

  function renderScoreOnJobCard(result = {}) {
    const entry = findCardForJob(result);
    const card = entry?.card;
    if (!card) return { ok: false, reason: 'CARD_NOT_FOUND' };

    ensureCardScoreStyle();
    card.classList.add('hiflow-job-card-scored');
    card.setAttribute('data-hiflow-score', String(Number(result.score || 0)));

    const previous = card.querySelector(':scope > .hiflow-job-score-badge');
    if (previous) previous.remove();

    const badge = document.createElement('div');
    const tone = getScoreTone(result);
    badge.className = `hiflow-job-score-badge is-${tone}`;
    badge.setAttribute('aria-label', `HiFlow 匹配分 ${Number(result.score || 0)}%`);
    badge.innerHTML = `
      <strong>${Number(result.score || 0)}%</strong>
      <span>${tone === 'ok' ? '可沟通' : tone === 'warn' ? '待确认' : '偏低'}</span>
    `;
    card.appendChild(badge);

    return { ok: true };
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

  async function prepareGreetingForJobs(jobs = []) {
    const actions = [];

    for (const job of jobs) {
      if (job.current) {
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
        await window.HiFlowDom.sleep(900);

        actions.push({
          id: job.id,
          status: 'BOSS_GREETING_TRIGGERED',
          title: job.jobMeta?.title || '',
          message: '匹配通过，已点击 BOSS 沟通/打招呼按钮'
        });
        continue;
      }

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
      await window.HiFlowDom.sleep(900);

      actions.push({
        id: job.id,
        status: 'BOSS_GREETING_TRIGGERED',
        title: job.jobMeta?.title || '',
        message: '已点击 BOSS 沟通/打招呼按钮'
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
      prepareGreetingForJobs(message.jobs || []).then(sendResponse).catch(error => {
        sendResponse({ ok: false, error: error.message });
      });
      return true;
    }

    if (message.type === 'HIFLOW_RENDER_JOB_SCORE') {
      sendResponse(renderScoreOnJobCard(message.result || {}));
      return false;
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
