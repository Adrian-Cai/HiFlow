(function () {
  'use strict';

  const ROOT_ID = 'hiflow-floating-root';
  const PANEL_STATE_KEY = 'hiflow.panelCollapsed';

  if (document.getElementById(ROOT_ID)) return;

  const host = document.createElement('div');
  host.id = ROOT_ID;
  document.documentElement.appendChild(host);

  const shadow = host.attachShadow({ mode: 'open' });
  let els = {};
  let isCollapsed = false;

  init().catch(error => {
    console.warn('[HiFlow] floating panel failed:', error);
  });

  async function init() {
    const css = await loadPanelCss();
    shadow.innerHTML = `
      <style>${css}</style>
      <div class="hiflow-shell" data-hiflow-shell>
        <button id="hiflow-toggle" class="hiflow-toggle" type="button" aria-expanded="true">
          <span class="hiflow-toggle-dot" aria-hidden="true"></span>
          <span>HiFlow</span>
        </button>
        <aside class="hiflow-panel" aria-label="HiFlow 悬浮面板">
          <main class="hiflow-app">
            <header class="hiflow-topbar">
              <div>
                <h1 class="hiflow-title">HiFlow</h1>
                <p id="page-state" class="hiflow-subtitle">等待页面状态</p>
              </div>
              <div class="hiflow-header-actions">
                <span id="service-pill" class="hiflow-pill">未连接</span>
                <button id="collapse-panel" class="hiflow-button hiflow-icon-button" type="button" title="收起面板" aria-label="收起面板">×</button>
              </div>
            </header>

            <section class="hiflow-section" aria-labelledby="settings-title">
              <h2 id="settings-title" class="hiflow-section-title">配置</h2>
              <div class="hiflow-field">
                <label for="resume-id">简历 ID</label>
                <input id="resume-id" class="hiflow-input" type="text" autocomplete="off" />
              </div>
              <div class="hiflow-field">
                <label for="threshold">阈值</label>
                <input id="threshold" class="hiflow-input" type="number" min="0" max="100" step="1" />
              </div>
              <div class="hiflow-field">
                <label for="scan-limit">每批扫描数量</label>
                <input id="scan-limit" class="hiflow-input" type="number" min="1" max="20" step="1" />
              </div>
              <div class="hiflow-field">
                <label for="service-url">本地服务</label>
                <input id="service-url" class="hiflow-input" type="url" autocomplete="off" />
              </div>
              <label class="hiflow-check-row" for="auto-send">
                <input id="auto-send" type="checkbox" />
                <span>自动点击发送</span>
              </label>
              <button id="save-settings" class="hiflow-button" type="button">保存配置</button>
            </section>

            <section class="hiflow-section" aria-labelledby="resume-title">
              <div class="hiflow-section-head">
                <h2 id="resume-title" class="hiflow-section-title">我的简历画像</h2>
                <button id="load-resumes" class="hiflow-button secondary" type="button">读取</button>
              </div>
              <div class="hiflow-field">
                <label for="resume-name">名称</label>
                <input id="resume-name" class="hiflow-input" type="text" autocomplete="off" />
              </div>
              <div class="hiflow-field">
                <label for="resume-summary">简历摘要</label>
                <textarea id="resume-summary" class="hiflow-input hiflow-textarea" rows="5"></textarea>
              </div>
              <div class="hiflow-field">
                <label for="target-titles">目标岗位</label>
                <textarea id="target-titles" class="hiflow-input hiflow-textarea" rows="3"></textarea>
              </div>
              <div class="hiflow-field">
                <label for="resume-skills">技能关键词</label>
                <textarea id="resume-skills" class="hiflow-input hiflow-textarea" rows="5"></textarea>
              </div>
              <div class="hiflow-field">
                <label for="exclude-keywords">排除词</label>
                <textarea id="exclude-keywords" class="hiflow-input hiflow-textarea" rows="3"></textarea>
              </div>
              <button id="save-resume" class="hiflow-button" type="button">保存简历画像</button>
            </section>

            <section class="hiflow-section hiflow-action-grid" aria-label="岗位操作">
              <button id="analyze-current" class="hiflow-button" type="button">分析当前岗位</button>
              <button id="scan-visible" class="hiflow-button" type="button">扫描当前批次</button>
              <button id="scan-prepare" class="hiflow-button" type="button">扫描并准备打招呼</button>
              <button id="add-current" class="hiflow-button" type="button">加入当前岗位</button>
              <button id="add-scan" class="hiflow-button" type="button">加入推荐岗位</button>
              <button id="refresh-chat" class="hiflow-button" type="button">刷新 Chat 状态</button>
              <button id="clear-logs" class="hiflow-button secondary" type="button">清空日志</button>
            </section>

            <section class="hiflow-section" aria-labelledby="current-title">
              <h2 id="current-title" class="hiflow-section-title">当前匹配</h2>
              <div id="current-result" class="hiflow-empty" role="status">暂无匹配结果</div>
            </section>

            <section class="hiflow-section" aria-labelledby="scan-title">
              <div class="hiflow-section-head">
                <h2 id="scan-title" class="hiflow-section-title">扫描结果</h2>
                <span id="scan-count" class="hiflow-count">0</span>
              </div>
              <ol id="scan-results" class="hiflow-list"></ol>
            </section>

            <section class="hiflow-section" aria-labelledby="queue-title">
              <div class="hiflow-section-head">
                <h2 id="queue-title" class="hiflow-section-title">投递队列</h2>
                <span id="queue-count" class="hiflow-count">0</span>
              </div>
              <ol id="queue-list" class="hiflow-list"></ol>
            </section>

            <section class="hiflow-section" aria-labelledby="logs-title">
              <div class="hiflow-section-head">
                <h2 id="logs-title" class="hiflow-section-title">日志</h2>
                <span id="log-count" class="hiflow-count">0</span>
              </div>
              <ol id="logs" class="hiflow-log-list"></ol>
            </section>
          </main>
        </aside>
      </div>
    `;

    collectElements();
    bindEvents();
    await restorePanelState();
    await refresh();
  }

  async function loadPanelCss() {
    const url = chrome.runtime.getURL('content/floating-panel.css');
    try {
      const response = await fetch(url);
      if (response.ok) return response.text();
    } catch (error) {
      console.warn('[HiFlow] CSS load failed:', error);
    }

    return ':host{all:initial}.hiflow-shell{position:fixed;right:16px;top:76px;z-index:2147483647}.hiflow-panel{background:#fff;border:1px solid #ddd}.hiflow-app{padding:12px}';
  }

  function collectElements() {
    els = {
      shell: shadow.querySelector('[data-hiflow-shell]'),
      toggle: shadow.querySelector('#hiflow-toggle'),
      collapsePanel: shadow.querySelector('#collapse-panel'),
      pageState: shadow.querySelector('#page-state'),
      servicePill: shadow.querySelector('#service-pill'),
      resumeId: shadow.querySelector('#resume-id'),
      threshold: shadow.querySelector('#threshold'),
      scanLimit: shadow.querySelector('#scan-limit'),
      serviceUrl: shadow.querySelector('#service-url'),
      autoSend: shadow.querySelector('#auto-send'),
      saveSettings: shadow.querySelector('#save-settings'),
      loadResumes: shadow.querySelector('#load-resumes'),
      resumeName: shadow.querySelector('#resume-name'),
      resumeSummary: shadow.querySelector('#resume-summary'),
      targetTitles: shadow.querySelector('#target-titles'),
      resumeSkills: shadow.querySelector('#resume-skills'),
      excludeKeywords: shadow.querySelector('#exclude-keywords'),
      saveResume: shadow.querySelector('#save-resume'),
      analyzeCurrent: shadow.querySelector('#analyze-current'),
      scanVisible: shadow.querySelector('#scan-visible'),
      scanPrepare: shadow.querySelector('#scan-prepare'),
      addCurrent: shadow.querySelector('#add-current'),
      addScan: shadow.querySelector('#add-scan'),
      refreshChat: shadow.querySelector('#refresh-chat'),
      clearLogs: shadow.querySelector('#clear-logs'),
      currentResult: shadow.querySelector('#current-result'),
      scanCount: shadow.querySelector('#scan-count'),
      scanResults: shadow.querySelector('#scan-results'),
      queueCount: shadow.querySelector('#queue-count'),
      queueList: shadow.querySelector('#queue-list'),
      logCount: shadow.querySelector('#log-count'),
      logs: shadow.querySelector('#logs')
    };
  }

  function bindEvents() {
    els.toggle.addEventListener('click', () => setCollapsed(!isCollapsed, true));
    els.collapsePanel.addEventListener('click', () => setCollapsed(true, true));

    els.saveSettings.addEventListener('click', () => runAction(els.saveSettings, 'HIFLOW_UPDATE_SETTINGS', {
      localServiceUrl: els.serviceUrl.value.trim(),
      selectedResumeId: els.resumeId.value.trim(),
      threshold: Number(els.threshold.value || 90),
      scanLimit: Number(els.scanLimit.value || 8),
      autoSendGreeting: els.autoSend.checked
    }));

    els.loadResumes.addEventListener('click', () => runAction(els.loadResumes, 'HIFLOW_REFRESH_RESUMES'));
    els.saveResume.addEventListener('click', () => runAction(els.saveResume, 'HIFLOW_SAVE_RESUME', {
      id: els.resumeId.value.trim(),
      name: els.resumeName.value.trim(),
      summary: els.resumeSummary.value.trim(),
      targetTitles: els.targetTitles.value.trim(),
      skills: els.resumeSkills.value.trim(),
      excludeKeywords: els.excludeKeywords.value.trim()
    }));
    els.analyzeCurrent.addEventListener('click', () => runAction(els.analyzeCurrent, 'HIFLOW_ANALYZE_CURRENT'));
    els.scanVisible.addEventListener('click', () => runAction(els.scanVisible, 'HIFLOW_SCAN_VISIBLE'));
    els.scanPrepare.addEventListener('click', () => runAction(els.scanPrepare, 'HIFLOW_SCAN_AND_PREPARE_GREETING'));
    els.addCurrent.addEventListener('click', () => runAction(els.addCurrent, 'HIFLOW_ADD_CURRENT_TO_QUEUE'));
    els.addScan.addEventListener('click', () => runAction(els.addScan, 'HIFLOW_ADD_SCAN_RECOMMENDED'));
    els.refreshChat.addEventListener('click', () => runAction(els.refreshChat, 'HIFLOW_REFRESH_CHAT'));
    els.clearLogs.addEventListener('click', () => runAction(els.clearLogs, 'HIFLOW_CLEAR_LOGS'));

    chrome.storage.onChanged.addListener((changes, areaName) => {
      if (areaName === 'local' && Object.keys(changes).some(key => key.startsWith('hiflow.'))) {
        refresh();
      }
    });

    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
      if (message?.type !== 'HIFLOW_TOGGLE_FLOATING_PANEL') return false;
      setCollapsed(!isCollapsed, true);
      refresh();
      sendResponse({ ok: true, collapsed: isCollapsed });
      return false;
    });
  }

  async function restorePanelState() {
    const stored = await chrome.storage.local.get(PANEL_STATE_KEY);
    setCollapsed(Boolean(stored[PANEL_STATE_KEY]), false);
  }

  function setCollapsed(nextCollapsed, persist) {
    isCollapsed = Boolean(nextCollapsed);
    els.shell.classList.toggle('is-collapsed', isCollapsed);
    els.toggle.setAttribute('aria-expanded', String(!isCollapsed));
    els.toggle.querySelector('span:last-child').textContent = isCollapsed ? 'HiFlow' : 'HiFlow 已展开';

    if (persist) {
      chrome.storage.local.set({ [PANEL_STATE_KEY]: isCollapsed }).catch(() => {});
    }
  }

  async function refresh() {
    try {
      const state = await sendMessage({ type: 'HIFLOW_GET_STATE' });
      if (state?.ok) render(state);
    } catch (error) {
      renderError(error.message);
    }
  }

  async function runAction(button, type, payload = undefined) {
    setBusy(button, true);
    try {
      const state = await sendMessage({ type, payload });
      if (state?.ok) render(state);
      if (!state?.ok && state?.error) renderError(state.error);
    } catch (error) {
      renderError(error.message);
    } finally {
      setBusy(button, false);
    }
  }

  function sendMessage(message) {
    return chrome.runtime.sendMessage(message);
  }

  function setBusy(button, isBusy) {
    if (!button) return;
    button.disabled = isBusy;
    button.setAttribute('aria-busy', String(isBusy));
  }

  function render(state) {
    const settings = state.settings || {};
    els.resumeId.value = settings.selectedResumeId || '';
    els.threshold.value = Number(settings.threshold || 90);
    els.scanLimit.value = Number(settings.scanLimit || 8);
    els.serviceUrl.value = settings.localServiceUrl || '';
    els.autoSend.checked = Boolean(settings.autoSendGreeting);

    renderResumeEditor(state.resumes || [], settings.selectedResumeId);
    renderServicePill(state);
    renderPageState(state.pageState);
    renderCurrent(state.currentResult);
    renderScanResults(state.scanResults || []);
    renderQueue(state.queue || []);
    renderLogs(state.logs || []);
  }

  function renderResumeEditor(resumes, selectedResumeId) {
    if (!resumes.length) return;

    const selected = resumes.find(resume => resume.id === selectedResumeId) || resumes[0];
    if (!selected) return;

    els.resumeId.value = selected.id || selectedResumeId || '';
    els.resumeName.value = selected.name || '';
    els.resumeSummary.value = selected.summary || '';
    els.targetTitles.value = (selected.target_titles || selected.targetTitles || []).join('\n');
    els.resumeSkills.value = (selected.skills || []).join('\n');
    els.excludeKeywords.value = (selected.exclude_keywords || selected.excludeKeywords || []).join('\n');
  }

  function renderServicePill(state) {
    const logs = state.logs || [];
    const hasServiceError = logs.some(log => /匹配服务|fetch|Failed|返回/.test(log.message || ''));
    els.servicePill.textContent = hasServiceError ? '需检查' : '就绪';
    els.servicePill.className = `hiflow-pill ${hasServiceError ? 'bad' : 'ok'}`;
  }

  function renderPageState(pageState) {
    if (!pageState) {
      els.pageState.textContent = '等待页面状态';
      return;
    }

    const page = pageState.page || (pageState.contact ? 'chat' : 'jobs');
    els.pageState.textContent = page === 'chat'
      ? `Chat: ${pageState.contact || pageState.title || '当前会话'}`
      : `Jobs: ${pageState.title || 'BOSS 岗位页'}`;
  }

  function renderCurrent(result) {
    if (!result) {
      els.currentResult.className = 'hiflow-empty';
      els.currentResult.textContent = '暂无匹配结果';
      return;
    }

    els.currentResult.className = '';
    const job = result.jobMeta || {};
    const decisionClass = result.decision === 'RECOMMEND' ? 'ok' : 'bad';
    els.currentResult.innerHTML = `
      <div class="hiflow-score-row">
        <div>
          <div class="hiflow-item-title">${escapeHtml(job.title || '未识别岗位')}</div>
          <div class="hiflow-meta">${escapeHtml([job.company, job.salary, job.location].filter(Boolean).join(' / ') || '无岗位信息')}</div>
        </div>
        <div class="hiflow-score">${Number(result.score || 0)}%</div>
      </div>
      <div class="hiflow-decision ${decisionClass}">${result.decision === 'RECOMMEND' ? '推荐沟通' : '暂不推荐'}</div>
      <div class="hiflow-points">
        ${renderPointLine('匹配', result.matchedPoints)}
        ${renderPointLine('缺口', result.missingPoints)}
        ${renderPointLine('风险', result.riskPoints)}
      </div>
    `;
  }

  function renderScanResults(results) {
    els.scanCount.textContent = String(results.length);
    els.scanResults.innerHTML = results.length
      ? results.map(renderResultItem).join('')
      : '<li class="hiflow-empty">暂无扫描结果</li>';
  }

  function renderQueue(queue) {
    els.queueCount.textContent = String(queue.length);
    els.queueList.innerHTML = queue.length
      ? queue.map(item => {
        const job = item.jobMeta || {};
        return `
          <li class="hiflow-item">
            <div class="hiflow-item-line">
              <span class="hiflow-item-title">${escapeHtml(job.title || '未识别岗位')}</span>
              <span class="hiflow-count">${Number(item.score || 0)}%</span>
            </div>
            <div class="hiflow-meta">${escapeHtml([job.company, job.salary, job.location].filter(Boolean).join(' / ') || '无岗位信息')}</div>
            <div class="hiflow-meta">${escapeHtml(formatQueueStatus(item.status || 'PENDING_APPLY'))}</div>
            ${item.lastActionMessage ? `<div class="hiflow-meta">${escapeHtml(item.lastActionMessage)}</div>` : ''}
          </li>
        `;
      }).join('')
      : '<li class="hiflow-empty">暂无投递队列</li>';
  }

  function renderLogs(logs) {
    els.logCount.textContent = String(logs.length);
    els.logs.innerHTML = logs.length
      ? logs.slice(0, 20).map(log => `
        <li class="hiflow-log-item">
          ${escapeHtml(log.message || '')}
          <span class="hiflow-log-time">${formatTime(log.at)}</span>
        </li>
      `).join('')
      : '<li class="hiflow-empty">暂无日志</li>';
  }

  function renderResultItem(result) {
    const job = result.jobMeta || {};
    const decisionClass = result.decision === 'RECOMMEND' ? 'ok' : 'bad';
    return `
      <li class="hiflow-item">
        <div class="hiflow-item-line">
          <span class="hiflow-item-title">${escapeHtml(job.title || '未识别岗位')}</span>
          <span class="hiflow-count">${Number(result.score || 0)}%</span>
        </div>
        <div class="hiflow-meta">${escapeHtml([job.company, job.salary, job.location].filter(Boolean).join(' / ') || '无岗位信息')}</div>
        <div class="hiflow-decision ${decisionClass}">${result.decision === 'RECOMMEND' ? '推荐沟通' : '暂不推荐'}</div>
      </li>
    `;
  }

  function renderPointLine(label, points = []) {
    const text = Array.isArray(points) && points.length ? points.slice(0, 3).join('、') : '暂无';
    return `<div><b>${label}：</b>${escapeHtml(text)}</div>`;
  }

  function renderError(message) {
    els.servicePill.textContent = '异常';
    els.servicePill.className = 'hiflow-pill bad';
    els.currentResult.className = 'hiflow-empty';
    els.currentResult.textContent = message || '操作失败';
  }

  function formatTime(value) {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString('zh-CN', { hour12: false });
  }

  function formatQueueStatus(status) {
    return ({
      PENDING_APPLY: '待准备打招呼',
      PENDING_SEND_CONFIRM: '已填入话术，待人工发送',
      PENDING_SECOND: '已发送第一条，待第二轮跟进',
      NEED_MANUAL_INPUT: '需手动补充话术',
      NEED_MANUAL_SEND: '已填入话术，需手动发送',
      APPLY_FAILED: '准备失败'
    })[status] || status;
  }

  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, char => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#039;'
    })[char]);
  }
})();
