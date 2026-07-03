(function () {
  'use strict';

  function collectChatState() {
    const root = document.body;
    const text = window.HiFlowDom.getCleanTextFromElement(root);
    const titleSelectors = [
      '.chat-name',
      '.user-name',
      '.name',
      '[class*="chat"] [class*="name"]',
      '[class*="user"] [class*="name"]'
    ];

    let contact = '';
    for (const selector of titleSelectors) {
      const value = (document.querySelector(selector)?.innerText || '').trim();
      if (value && value.length <= 60) {
        contact = value;
        break;
      }
    }

    return {
      ok: true,
      page: 'chat',
      chat: {
        contact,
        title: document.title,
        url: location.href,
        textPreview: text.slice(0, 1200),
        collectedAt: new Date().toISOString()
      }
    };
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (!message || !message.type) return false;

    if (message.type === 'HIFLOW_COLLECT_CHAT_STATE') {
      try {
        sendResponse(collectChatState());
      } catch (error) {
        sendResponse({ ok: false, error: error.message });
      }
      return false;
    }

    return false;
  });

  chrome.runtime.sendMessage({
    type: 'HIFLOW_PAGE_READY',
    payload: {
      page: 'chat',
      url: location.href,
      title: document.title
    }
  }).catch(() => {});
})();
