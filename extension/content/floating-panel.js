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
  let currentPageType = '';
  let activeTab = 'match';

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
              <div class="hiflow-brand">
                <span class="hiflow-logo" aria-hidden="true">Hi</span>
                <h1 class="hiflow-title">HiFlow</h1>
              </div>
              <div class="hiflow-header-actions">
                <span id="service-pill" class="hiflow-service-pill" role="status" aria-live="polite">
                  <span class="hiflow-service-dot" aria-hidden="true"></span>
                  <span>本地服务</span>
                  <b>未连接</b>
                </span>
                <button id="collapse-panel" class="hiflow-icon-button" type="button" title="收起面板" aria-label="收起面板">
                  ${icon('x')}
                </button>
              </div>
            </header>

            <section class="hiflow-control-strip hiflow-control-strip-compact" aria-label="匹配配置">
              <label class="hiflow-control-pill" for="resume-id">
                <span>简历</span>
                <input id="resume-id" class="hiflow-inline-input" type="text" autocomplete="off" />
                <span class="hiflow-verified" aria-hidden="true">${icon('check-mini')}</span>
              </label>
              <label class="hiflow-control-pill hiflow-number-pill" for="threshold">
                <span class="hiflow-pill-icon" aria-hidden="true">${icon('target')}</span>
                <span>阈值</span>
                <input id="threshold" class="hiflow-inline-input" type="number" min="0" max="100" step="1" />
              </label>
            </section>

            <nav class="hiflow-nav hiflow-nav-compact" role="tablist" aria-label="HiFlow 导航">
              <button id="tab-match" class="hiflow-nav-item is-active" type="button" role="tab" aria-selected="true" aria-controls="panel-match" data-tab="match">
                ${icon('home')}<span>匹配</span>
              </button>
              <button id="tab-resume" class="hiflow-nav-item" type="button" role="tab" aria-selected="false" aria-controls="panel-resume" data-tab="resume">
                ${icon('file')}<span>简历</span>
              </button>
              <button id="tab-settings" class="hiflow-nav-item" type="button" role="tab" aria-selected="false" aria-controls="panel-settings" data-tab="settings">
                ${icon('settings')}<span>设置</span>
              </button>
              <button id="tab-logs" class="hiflow-nav-item" type="button" role="tab" aria-selected="false" aria-controls="panel-logs" data-tab="logs">
                ${icon('list')}<span>日志</span>
              </button>
            </nav>

            <div id="panel-match" class="hiflow-tab-panel is-active" role="tabpanel" aria-labelledby="tab-match" data-tab-panel="match">
              <section id="overview" class="hiflow-match-card" aria-labelledby="current-title">
                <div class="hiflow-match-head">
                  <div>
                    <p class="hiflow-eyebrow">当前岗位匹配</p>
                    <h2 id="current-title" class="hiflow-job-title">等待岗位</h2>
                  </div>
                  <div class="hiflow-person-line">
                    <span id="page-state">等待页面状态</span>
                    <span id="current-location">--</span>
                  </div>
                </div>
                <div id="current-result" class="hiflow-current-body" role="status">暂无匹配结果</div>
              </section>

              <section id="actions" class="hiflow-action-grid hiflow-action-grid-compact" aria-label="当前岗位操作">
                ${actionButton('capture-resume-primary', 'file', '获取简历信息')}
                ${actionButton('analyze-current', 'bar-chart', '分析当前岗位')}
                ${actionButton('prepare-current', 'message', '匹配高则点沟通')}
              </section>
            </div>

            <div id="panel-resume" class="hiflow-tab-panel" role="tabpanel" aria-labelledby="tab-resume" data-tab-panel="resume" hidden>
              <details id="resume-details" class="hiflow-accordion" open>
                <summary>
                  <span>简历画像</span>
                  <span id="resume-capture-pill" class="hiflow-count">未识别</span>
                </summary>
                <section class="hiflow-accordion-body" aria-labelledby="resume-title">
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
                  <div class="hiflow-split-actions">
                    <button id="save-resume" class="hiflow-button" type="button">保存简历画像</button>
                    <button id="open-resume-page" class="hiflow-button secondary" type="button">打开简历页</button>
                    <button id="capture-resume" class="hiflow-button secondary" type="button">识别并保存</button>
                  </div>
                  <div id="resume-capture-status" class="hiflow-empty" role="status">暂无简历页数据</div>
                </section>
              </details>
            </div>

            <div id="panel-settings" class="hiflow-tab-panel" role="tabpanel" aria-labelledby="tab-settings" data-tab-panel="settings" hidden>
              <details id="settings-details" class="hiflow-accordion" open>
                <summary>
                  <span>配置</span>
                  <span class="hiflow-count">已保存</span>
                </summary>
                <section class="hiflow-accordion-body" aria-labelledby="settings-title">
                  <h2 id="settings-title" class="hiflow-section-title">运行配置</h2>
                  <div class="hiflow-field">
                    <label for="service-url">本地服务</label>
                    <input id="service-url" class="hiflow-input" type="url" autocomplete="off" />
                  </div>
                  <div class="hiflow-note">匹配通过后仅点击 BOSS 的沟通/打招呼按钮，不填入话术，不点击发送。</div>
                  <button id="save-settings" class="hiflow-button" type="button">保存配置</button>
                </section>
              </details>
            </div>

            <div id="panel-logs" class="hiflow-tab-panel" role="tabpanel" aria-labelledby="tab-logs" data-tab-panel="logs" hidden>
              <details id="logs-details" class="hiflow-accordion hiflow-log-accordion" open>
                <summary>
                  <span>日志</span>
                  <span id="log-count" class="hiflow-count">0</span>
                </summary>
                <section class="hiflow-accordion-body" aria-labelledby="logs-title">
                  <div class="hiflow-section-head">
                    <h2 id="logs-title" class="hiflow-section-title">运行日志</h2>
                    <button id="clear-logs" class="hiflow-button secondary" type="button">清空</button>
                  </div>
                  <ol id="logs" class="hiflow-log-list"></ol>
                </section>
              </details>
            </div>
          </main>
        </aside>
      </div>
    `;

    collectElements();
    setActiveTab(activeTab);
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

    return ':host{all:initial}.hiflow-shell{position:fixed;right:16px;top:32px;z-index:2147483647}.hiflow-panel{background:#fff;border:1px solid #ddd}.hiflow-app{padding:12px}';
  }

  function collectElements() {
    els = {
      shell: shadow.querySelector('[data-hiflow-shell]'),
      app: shadow.querySelector('.hiflow-app'),
      toggle: shadow.querySelector('#hiflow-toggle'),
      collapsePanel: shadow.querySelector('#collapse-panel'),
      navItems: Array.from(shadow.querySelectorAll('.hiflow-nav-item')),
      tabPanels: Array.from(shadow.querySelectorAll('[data-tab-panel]')),
      pageState: shadow.querySelector('#page-state'),
      servicePill: shadow.querySelector('#service-pill'),
      currentLocation: shadow.querySelector('#current-location'),
      currentTitle: shadow.querySelector('#current-title'),
      resumeId: shadow.querySelector('#resume-id'),
      threshold: shadow.querySelector('#threshold'),
      serviceUrl: shadow.querySelector('#service-url'),
      saveSettings: shadow.querySelector('#save-settings'),
      loadResumes: shadow.querySelector('#load-resumes'),
      resumeName: shadow.querySelector('#resume-name'),
      resumeSummary: shadow.querySelector('#resume-summary'),
      targetTitles: shadow.querySelector('#target-titles'),
      resumeSkills: shadow.querySelector('#resume-skills'),
      excludeKeywords: shadow.querySelector('#exclude-keywords'),
      saveResume: shadow.querySelector('#save-resume'),
      openResumePage: shadow.querySelector('#open-resume-page'),
      captureResume: shadow.querySelector('#capture-resume'),
      captureResumePrimary: shadow.querySelector('#capture-resume-primary'),
      resumeCapturePill: shadow.querySelector('#resume-capture-pill'),
      resumeCaptureStatus: shadow.querySelector('#resume-capture-status'),
      analyzeCurrent: shadow.querySelector('#analyze-current'),
      prepareCurrent: shadow.querySelector('#prepare-current'),
      currentResult: shadow.querySelector('#current-result'),
      logCount: shadow.querySelector('#log-count'),
      clearLogs: shadow.querySelector('#clear-logs'),
      logs: shadow.querySelector('#logs')
    };
  }

  function bindEvents() {
    els.toggle.addEventListener('click', () => setCollapsed(!isCollapsed, true));
    els.collapsePanel.addEventListener('click', () => setCollapsed(true, true));

    els.navItems.forEach(button => {
      button.addEventListener('click', () => setActiveTab(button.dataset.tab));
    });

    els.saveSettings.addEventListener('click', () => runAction(els.saveSettings, 'HIFLOW_UPDATE_SETTINGS', {
      localServiceUrl: els.serviceUrl.value.trim(),
      selectedResumeId: els.resumeId.value.trim(),
      threshold: Number(els.threshold.value || 90),
      autoSendGreeting: false
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
    els.openResumePage.addEventListener('click', () => runAction(els.openResumePage, 'HIFLOW_OPEN_RESUME_PAGE'));
    els.captureResume.addEventListener('click', () => runAction(els.captureResume, 'HIFLOW_CAPTURE_RESUME_PROFILE'));
    els.captureResumePrimary.addEventListener('click', () => {
      const type = currentPageType === 'resume' ? 'HIFLOW_CAPTURE_RESUME_PROFILE' : 'HIFLOW_OPEN_RESUME_PAGE';
      runAction(els.captureResumePrimary, type);
    });
    els.analyzeCurrent.addEventListener('click', () => runAction(els.analyzeCurrent, 'HIFLOW_ANALYZE_CURRENT'));
    els.prepareCurrent.addEventListener('click', () => runAction(els.prepareCurrent, 'HIFLOW_ANALYZE_AND_PREPARE_CURRENT'));
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

  function setActiveTab(nextTab) {
    if (!nextTab) return;
    activeTab = nextTab;

    els.navItems.forEach(item => {
      const isActive = item.dataset.tab === activeTab;
      item.classList.toggle('is-active', isActive);
      item.setAttribute('aria-selected', String(isActive));
    });

    els.tabPanels.forEach(panel => {
      const isActive = panel.dataset.tabPanel === activeTab;
      panel.hidden = !isActive;
      panel.classList.toggle('is-active', isActive);
      if (isActive) {
        panel.querySelectorAll('details').forEach(details => {
          details.open = true;
        });
      }
    });

    if (els.app) els.app.scrollTop = 0;
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
    els.serviceUrl.value = settings.localServiceUrl || '';

    renderResumeEditor(state.resumes || [], settings.selectedResumeId);
    renderResumeCapture(state.resumeCapture);
    renderServicePill(state);
    renderPageState(state.pageState);
    renderCurrent(state.currentResult, state.pageState);
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

  function renderResumeCapture(capture) {
    if (!capture) {
      els.resumeCapturePill.textContent = '未识别';
      els.resumeCaptureStatus.className = 'hiflow-empty';
      els.resumeCaptureStatus.textContent = '暂无简历页数据';
      return;
    }

    const statusText = ({
      OPENING: '已打开',
      NEEDS_RESUME_PAGE: '待进入',
      EMPTY: '未识别',
      SAVE_FAILED: '保存失败',
      SAVED: '已保存'
    })[capture.status] || '处理中';

    els.resumeCapturePill.textContent = statusText;
    els.resumeCaptureStatus.className = 'hiflow-empty';

    if (capture.status === 'SAVED') {
      const titles = Array.isArray(capture.targetTitles) && capture.targetTitles.length
        ? `目标：${capture.targetTitles.slice(0, 3).join('、')}`
        : '目标：未识别';
      els.resumeCaptureStatus.innerHTML = `
        <div class="hiflow-item-title">${escapeHtml(capture.name || 'BOSS 在线简历')}</div>
        <div class="hiflow-meta">${escapeHtml(titles)}</div>
        <div class="hiflow-meta">${escapeHtml(`技能 ${Number(capture.skillsCount || 0)} 个 / 摘要 ${Number(capture.summaryLength || 0)} 字`)}</div>
      `;
      return;
    }

    els.resumeCaptureStatus.textContent = capture.message || '暂无简历页数据';
  }

  function renderServicePill(state) {
    const logs = state.logs || [];
    const hasServiceError = logs.some(log => /匹配服务|fetch|Failed|返回/.test(log.message || ''));
    els.servicePill.className = `hiflow-service-pill ${hasServiceError ? 'bad' : 'ok'}`;
    els.servicePill.innerHTML = `
      <span class="hiflow-service-dot" aria-hidden="true"></span>
      <span>本地服务</span>
      <b>${hasServiceError ? '需检查' : '运行中'}</b>
    `;
  }

  function renderPageState(pageState) {
    if (!pageState) {
      els.pageState.textContent = '等待页面状态';
      return;
    }

    const page = pageState.page || (pageState.contact ? 'chat' : 'jobs');
    currentPageType = page;
    if (page === 'chat') {
      els.pageState.textContent = `${pageState.contact || pageState.title || '当前会话'} · 在线`;
      return;
    }
    if (page === 'resume') {
      els.pageState.textContent = pageState.title || 'BOSS 简历页';
      return;
    }

    els.pageState.textContent = pageState.title || 'BOSS 岗位页';
  }

  function renderCurrent(result, pageState) {
    if (!result) {
      els.currentTitle.textContent = '等待岗位';
      els.currentLocation.textContent = '--';
      els.currentResult.className = 'hiflow-current-body hiflow-empty-state';
      els.currentResult.textContent = '暂无匹配结果';
      return;
    }

    const job = result.jobMeta || {};
    const score = Number(result.score || 0);
    const matched = normalizePoints(result.matchedPoints);
    const missing = normalizePoints(result.missingPoints);
    const risks = normalizePoints(result.riskPoints);

    els.currentTitle.textContent = job.title || '未识别岗位';
    els.currentLocation.textContent = job.location || pageState?.location || '--';
    els.currentResult.className = 'hiflow-current-body';
    els.currentResult.innerHTML = `
      <div class="hiflow-current-copy">
        <h3>${escapeHtml(job.company || '未识别公司')}</h3>
        <p>${escapeHtml(formatJobMeta(job))}</p>
        <p>${escapeHtml(formatSkills(matched))}</p>
      </div>
      <div class="hiflow-score-block">
        <strong>${score}%</strong>
        <span>${result.decision === 'RECOMMEND' ? '可打招呼' : '暂不建议'}</span>
      </div>
      ${renderScoreBreakdown(result.detail)}
      <div class="hiflow-metric-row">
        ${metricCard('check', '匹配', matched.length ? String(matched.length) : '暂无', 'ok')}
        ${metricCard('alert', '缺口', missing.length ? String(missing.length) : '暂无', 'warn')}
        ${metricCard('shield', '风险', risks.length ? String(risks.length) : '暂无', 'ok')}
      </div>
      <div class="hiflow-point-grid">
        ${pointPanel('匹配明细', matched, '暂无匹配明细')}
        ${pointPanel('缺口明细', missing, '暂无明显缺口')}
        ${pointPanel('风险明细', risks, '暂无明显风险')}
      </div>
    `;
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

  function metricCard(iconName, label, value, tone) {
    return `
      <div class="hiflow-metric ${tone}">
        <span aria-hidden="true">${icon(iconName)}</span>
        <div>
          <small>${label}</small>
          <strong>${value}</strong>
        </div>
      </div>
    `;
  }

  function renderScoreBreakdown(detail = {}) {
    const rows = [
      ['硬性条件', detail.hardScore, '排除词、强约束'],
      ['岗位方向', detail.titleScore, '目标岗位命中'],
      ['技能覆盖', detail.skillScore, '简历技能与 JD 交集'],
      ['排除项', detail.conditionScore, '未命中排除词'],
      ['规则语义', detail.llmScore, '本地规则补充分']
    ].filter(([, value]) => value !== undefined && value !== null);

    if (!rows.length) return '';

    return `
      <section class="hiflow-score-detail" aria-label="评分依据">
        <div class="hiflow-score-detail-head">
          <span>评分依据</span>
          <b>${escapeHtml(formatScoreSource(detail.source))}</b>
        </div>
        <p>综合分 = 硬性条件 28% + 岗位方向 22% + 技能覆盖 30% + 排除项 12% + 规则语义 8%</p>
        <div class="hiflow-score-parts">
          ${rows.map(([label, value, hint]) => `
            <div>
              <span>${escapeHtml(label)}</span>
              <strong>${Number(value)}%</strong>
              <small>${escapeHtml(hint)}</small>
            </div>
          `).join('')}
        </div>
      </section>
    `;
  }

  function pointPanel(title, points, emptyText) {
    const normalized = normalizePoints(points);
    return `
      <section class="hiflow-point-panel">
        <h3>${escapeHtml(title)}</h3>
        ${normalized.length
          ? `<ul>${normalized.map(point => `<li>${escapeHtml(point)}</li>`).join('')}</ul>`
          : `<p>${escapeHtml(emptyText || '暂无')}</p>`}
      </section>
    `;
  }

  function normalizePoints(points) {
    return Array.isArray(points) ? points.filter(Boolean) : [];
  }

  function formatSkills(points) {
    if (!points.length) return '技能：待分析';
    return `技能：${points.slice(0, 3).join(' · ')}`;
  }

  function formatJobMeta(job) {
    return [job.salary, job.location, job.experience, job.education]
      .filter(Boolean)
      .join(' · ');
  }

  function formatScoreSource(source) {
    return source === 'local-rule-engine' ? '本地规则引擎' : (source || '本地匹配服务');
  }

  function renderError(message) {
    els.servicePill.className = 'hiflow-service-pill bad';
    els.servicePill.innerHTML = `
      <span class="hiflow-service-dot" aria-hidden="true"></span>
      <span>本地服务</span>
      <b>异常</b>
    `;
    els.currentResult.className = 'hiflow-current-body hiflow-empty-state';
    els.currentResult.textContent = message || '操作失败';
  }

  function formatTime(value) {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString('zh-CN', { hour12: false });
  }

  function actionButton(id, iconName, label) {
    return `
      <button id="${id}" class="hiflow-action-button" type="button">
        <span aria-hidden="true">${icon(iconName)}</span>
        <b>${label}</b>
      </button>
    `;
  }

  function icon(name) {
    const icons = {
      home: '<svg viewBox="0 0 24 24"><path d="M3 11.5 12 4l9 7.5"/><path d="M5 10.5V20h5v-5h4v5h5v-9.5"/></svg>',
      file: '<svg viewBox="0 0 24 24"><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/><path d="M8 13h8"/><path d="M8 17h5"/></svg>',
      settings: '<svg viewBox="0 0 24 24"><path d="M12 15.5A3.5 3.5 0 1 0 12 8a3.5 3.5 0 0 0 0 7.5Z"/><path d="M19.4 15a1.8 1.8 0 0 0 .36 2l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.8 1.8 0 0 0-2-.36 1.8 1.8 0 0 0-1.1 1.65V21a2 2 0 1 1-4 0v-.09A1.8 1.8 0 0 0 8.7 19.3a1.8 1.8 0 0 0-2 .36l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.8 1.8 0 0 0 .36-2A1.8 1.8 0 0 0 2.6 13H2.5a2 2 0 1 1 0-4h.09A1.8 1.8 0 0 0 4.2 7.9a1.8 1.8 0 0 0-.36-2l-.06-.06A2 2 0 1 1 6.6 3l.06.06a1.8 1.8 0 0 0 2 .36A1.8 1.8 0 0 0 9.8 1.8V1.7a2 2 0 1 1 4 0v.09a1.8 1.8 0 0 0 1.1 1.65 1.8 1.8 0 0 0 2-.36l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.8 1.8 0 0 0-.36 2 1.8 1.8 0 0 0 1.65 1.1H21a2 2 0 1 1 0 4h-.09A1.8 1.8 0 0 0 19.4 15Z"/></svg>',
      target: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/></svg>',
      'bar-chart': '<svg viewBox="0 0 24 24"><path d="M4 19V5"/><path d="M20 19H4"/><path d="M8 16v-5"/><path d="M12 16V8"/><path d="M16 16v-3"/></svg>',
      message: '<svg viewBox="0 0 24 24"><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"/><path d="M8 9h8"/><path d="M8 13h5"/></svg>',
      list: '<svg viewBox="0 0 24 24"><path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/><path d="M3 12h.01"/><path d="M3 18h.01"/></svg>',
      check: '<svg viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5"/></svg>',
      'check-mini': '<svg viewBox="0 0 16 16"><path d="m12.5 5-5.2 5.2L4.5 7.4"/></svg>',
      alert: '<svg viewBox="0 0 24 24"><path d="m12 3 10 18H2L12 3Z"/><path d="M12 9v5"/><path d="M12 17h.01"/></svg>',
      shield: '<svg viewBox="0 0 24 24"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="M12 8v5"/><path d="M12 16h.01"/></svg>',
      x: '<svg viewBox="0 0 24 24"><path d="M18 6 6 18"/><path d="M6 6l12 12"/></svg>'
    };
    return icons[name] || icons.home;
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
