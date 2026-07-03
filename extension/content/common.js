(function () {
  'use strict';

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  function isVisible(el) {
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
  }

  function getCleanTextFromElement(el) {
    if (!el) return '';
    const clone = el.cloneNode(true);
    clone.querySelectorAll('script, style, noscript').forEach(node => node.remove());
    return (clone.innerText || '').replace(/\s+/g, ' ').trim();
  }

  function simpleText(str) {
    return String(str || '')
      .replace(/\s+/g, '')
      .replace(/[（）()【】\[\]「」《》<>，。,.、/\\|｜:：;；·•_\-]/g, '')
      .toLowerCase();
  }

  function pickText(root, selectors, maxLength = 100) {
    for (const selector of selectors) {
      const el = root?.querySelector(selector);
      const value = (el?.innerText || '').trim();
      if (value && value.length <= maxLength) return value;
    }
    return '';
  }

  function getRightDetailRoot() {
    const selectors = [
      '.job-detail',
      '.job-detail-box',
      '.job-sec',
      '.job-detail-container',
      '[class*="job-detail"]',
      '[class*="detail"]'
    ];

    for (const selector of selectors) {
      const candidates = Array.from(document.querySelectorAll(selector))
        .filter(el => {
          const rect = el.getBoundingClientRect();
          const text = el.innerText || '';
          return isVisible(el) && rect.left > window.innerWidth * 0.3 && text.length > 120;
        })
        .sort((a, b) => (b.innerText || '').length - (a.innerText || '').length);

      if (candidates[0]) return candidates[0];
    }

    const candidates = Array.from(document.querySelectorAll('div, section, main'))
      .filter(el => {
        if (!isVisible(el)) return false;
        const rect = el.getBoundingClientRect();
        const text = el.innerText || '';
        return (
          rect.left > window.innerWidth * 0.35 &&
          rect.width > 320 &&
          rect.height > 240 &&
          text.length > 150 &&
          /职位描述|岗位职责|岗位要求|任职要求|工作地址|加分项/.test(text)
        );
      })
      .sort((a, b) => (b.innerText || '').length - (a.innerText || '').length);

    return candidates[0] || null;
  }

  function getCurrentJobSnapshot() {
    const root = getRightDetailRoot();
    const text = getCleanTextFromElement(root);
    const allLines = (root?.innerText || '')
      .split('\n')
      .map(x => x.trim())
      .filter(Boolean);

    const title = pickText(root, [
      '.job-title',
      '[class*="job-title"]',
      '.name',
      '[class*="name"]'
    ], 80);

    const company = pickText(root, [
      '.company-name',
      '[class*="company-name"]',
      '.company-info .name',
      '[class*="company"] .name'
    ], 80);

    const salary = allLines.find(x => /\d+\s*-\s*\d+\s*[Kk]|\d+\s*[Kk]/.test(x)) || '';
    const locationText = allLines.find(x => /上海|北京|深圳|广州|杭州|成都|武汉|南京|苏州|重庆|西安/.test(x)) || '';

    return {
      title,
      company,
      salary,
      location: locationText,
      text,
      url: window.location.href,
      collectedAt: new Date().toISOString()
    };
  }

  function getJobCards() {
    const selectors = [
      '.job-card-wrapper',
      '.job-card-body',
      '.search-job-result .job-card-wrapper',
      '.job-list-box .job-card-wrapper',
      'li[class*="job-card"]',
      'div[class*="job-card"]'
    ];

    const seen = new Set();
    const cards = [];

    selectors.forEach(selector => {
      document.querySelectorAll(selector).forEach(card => {
        if (seen.has(card)) return;
        const rect = card.getBoundingClientRect();
        const text = card.innerText || '';
        if (isVisible(card) && rect.left < window.innerWidth * 0.55 && text.length > 20) {
          seen.add(card);
          cards.push(card);
        }
      });
    });

    return cards;
  }

  function extractJobCardMeta(card) {
    const text = card?.innerText || '';
    const lines = text.split('\n').map(x => x.trim()).filter(Boolean);

    function pickBySelector(selectors) {
      for (const selector of selectors) {
        const value = (card?.querySelector(selector)?.innerText || '').trim();
        if (value) return value;
      }
      return '';
    }

    const title = pickBySelector([
      '.job-name',
      '.job-title',
      '[class*="job-name"]',
      '[class*="job-title"]',
      '.name'
    ]) || lines[0] || '';

    const salary = lines.find(x => /\d+\s*-\s*\d+\s*[Kk]|\d+\s*[Kk]/.test(x)) || '';
    const company = pickBySelector([
      '.company-name',
      '[class*="company-name"]',
      '.company-text',
      '[class*="company"]'
    ]) || lines.find(x => {
      return !x.includes(title) &&
        !x.includes(salary) &&
        x.length >= 2 &&
        x.length <= 40 &&
        !/本科|大专|硕士|经验|年|上海|北京|深圳|广州|杭州|JMeter|Postman|Python|测试/.test(x);
    }) || '';
    const locationText = lines.find(x => /上海|北京|深圳|广州|杭州|成都|武汉|南京|苏州|重庆|西安/.test(x)) || '';
    const link = card?.querySelector('a[href*="/job_detail/"]')?.href ||
      card?.closest('a[href*="/job_detail/"]')?.href ||
      location.href;

    return {
      title,
      company,
      salary,
      location: locationText,
      link,
      rawText: text
    };
  }

  function isRightDetailMatchedWithCard(snapshot = {}, cardMeta = {}) {
    const rightText = simpleText(snapshot.text || '');
    const rightTitle = simpleText(snapshot.title || '');
    const rightCompany = simpleText(snapshot.company || '');
    const cardTitle = simpleText(cardMeta.title || '');
    const cardCompany = simpleText(cardMeta.company || '');

    if (!rightText || !cardTitle) return false;
    if (rightText.includes(cardTitle) || rightTitle.includes(cardTitle) || cardTitle.includes(rightTitle)) return true;
    if (cardTitle.length >= 5 && rightText.includes(cardTitle.slice(0, 5))) return true;
    if (cardTitle.length >= 4 && rightTitle.includes(cardTitle.slice(0, 4))) return true;
    return Boolean(cardCompany && (rightText.includes(cardCompany) || rightCompany.includes(cardCompany)));
  }

  async function waitRightDetailReadyForCard(cardMeta, timeout = 7000) {
    const startedAt = Date.now();
    let lastSnapshot = null;

    while (Date.now() - startedAt < timeout) {
      await sleep(250);
      const snapshot = getCurrentJobSnapshot();
      lastSnapshot = snapshot;

      if (snapshot.text && snapshot.text.length >= 80 && isRightDetailMatchedWithCard(snapshot, cardMeta)) {
        return { ok: true, snapshot };
      }
    }

    return { ok: false, snapshot: lastSnapshot || getCurrentJobSnapshot() };
  }

  function getCurrentVisibleJobCards(limit = 15) {
    return getJobCards()
      .filter(card => {
        const rect = card.getBoundingClientRect();
        return rect.bottom > 80 && rect.top < window.innerHeight - 60;
      })
      .slice(0, limit);
  }

  window.HiFlowDom = {
    sleep,
    getCleanTextFromElement,
    getCurrentJobSnapshot,
    getCurrentVisibleJobCards,
    extractJobCardMeta,
    waitRightDetailReadyForCard
  };
})();
