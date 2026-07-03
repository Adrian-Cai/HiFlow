const els = {
  pageState: document.querySelector('#page-state'),
  servicePill: document.querySelector('#service-pill'),
  resumeId: document.querySelector('#resume-id'),
  threshold: document.querySelector('#threshold'),
  scanLimit: document.querySelector('#scan-limit'),
  serviceUrl: document.querySelector('#service-url'),
  autoSend: document.querySelector('#auto-send'),
  saveSettings: document.querySelector('#save-settings'),
  loadResumes: document.querySelector('#load-resumes'),
  resumeName: document.querySelector('#resume-name'),
  resumeSummary: document.querySelector('#resume-summary'),
  targetTitles: document.querySelector('#target-titles'),
  resumeSkills: document.querySelector('#resume-skills'),
  excludeKeywords: document.querySelector('#exclude-keywords'),
  saveResume: document.querySelector('#save-resume'),
  analyzeCurrent: document.querySelector('#analyze-current'),
  scanVisible: document.querySelector('#scan-visible'),
  scanPrepare: document.querySelector('#scan-prepare'),
  addCurrent: document.querySelector('#add-current'),
  addScan: document.querySelector('#add-scan'),
  refreshChat: document.querySelector('#refresh-chat'),
  clearLogs: document.querySelector('#clear-logs'),
  currentResult: document.querySelector('#current-result'),
  scanCount: document.querySelector('#scan-count'),
  scanResults: document.querySelector('#scan-results'),
  queueCount: document.querySelector('#queue-count'),
  queueList: document.querySelector('#queue-list'),
  logCount: document.querySelector('#log-count'),
  logs: document.querySelector('#logs')
};

const busyButtons = new Set();

document.addEventListener('DOMContentLoaded', () => {
  bindEvents();
  refresh();
});

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName === 'local' && Object.keys(changes).some(key => key.startsWith('hiflow.'))) {
    refresh();
  }
});

function bindEvents() {
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
}

async function refresh() {
  const state = await sendMessage({ type: 'HIFLOW_GET_STATE' });
  if (!state?.ok) return;
  render(state);
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
  if (isBusy) busyButtons.add(button);
  else busyButtons.delete(button);
  button.disabled = isBusy;
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
  els.servicePill.className = `pill ${hasServiceError ? 'bad' : 'ok'}`;
}

function renderPageState(pageState) {
  if (!pageState) {
    els.pageState.textContent = '等待页面状态';
    return;
  }

  const page = pageState.page || (pageState.contact ? 'chat' : 'jobs');
  const label = page === 'chat'
    ? `Chat: ${pageState.contact || pageState.title || '当前会话'}`
    : `Jobs: ${pageState.title || 'BOSS 岗位页'}`;
  els.pageState.textContent = label;
}

function renderCurrent(result) {
  if (!result) {
    els.currentResult.className = 'empty';
    els.currentResult.textContent = '暂无匹配结果';
    return;
  }

  els.currentResult.className = '';
  const job = result.jobMeta || {};
  const decisionClass = result.decision === 'RECOMMEND' ? 'ok' : 'bad';
  els.currentResult.innerHTML = `
    <div class="score-row">
      <div>
        <div class="item-title">${escapeHtml(job.title || '未识别岗位')}</div>
        <div class="meta">${escapeHtml([job.company, job.salary, job.location].filter(Boolean).join(' / ') || '无岗位信息')}</div>
      </div>
      <div class="score">${Number(result.score || 0)}%</div>
    </div>
    <div class="decision ${decisionClass}">${result.decision === 'RECOMMEND' ? '推荐沟通' : '暂不推荐'}</div>
    <div class="points">
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
    : '<li class="empty">暂无扫描结果</li>';
}

function renderQueue(queue) {
  els.queueCount.textContent = String(queue.length);
  els.queueList.innerHTML = queue.length
    ? queue.map(item => {
      const job = item.jobMeta || {};
      return `
        <li class="item">
          <div class="item-line">
            <span class="item-title">${escapeHtml(job.title || '未识别岗位')}</span>
            <span class="count">${Number(item.score || 0)}%</span>
          </div>
          <div class="meta">${escapeHtml([job.company, job.salary, job.location].filter(Boolean).join(' / ') || '无岗位信息')}</div>
          <div class="meta">${escapeHtml(formatQueueStatus(item.status || 'PENDING_APPLY'))}</div>
          ${item.lastActionMessage ? `<div class="meta">${escapeHtml(item.lastActionMessage)}</div>` : ''}
        </li>
      `;
    }).join('')
    : '<li class="empty">暂无投递队列</li>';
}

function renderLogs(logs) {
  els.logCount.textContent = String(logs.length);
  els.logs.innerHTML = logs.length
    ? logs.slice(0, 20).map(log => `
      <li class="log-item">
        ${escapeHtml(log.message || '')}
        <span class="log-time">${formatTime(log.at)}</span>
      </li>
    `).join('')
    : '<li class="empty">暂无日志</li>';
}

function renderResultItem(result) {
  const job = result.jobMeta || {};
  const decisionClass = result.decision === 'RECOMMEND' ? 'ok' : 'bad';
  return `
    <li class="item">
      <div class="item-line">
        <span class="item-title">${escapeHtml(job.title || '未识别岗位')}</span>
        <span class="count">${Number(result.score || 0)}%</span>
      </div>
      <div class="meta">${escapeHtml([job.company, job.salary, job.location].filter(Boolean).join(' / ') || '无岗位信息')}</div>
      <div class="decision ${decisionClass}">${result.decision === 'RECOMMEND' ? '推荐沟通' : '暂不推荐'}</div>
    </li>
  `;
}

function renderPointLine(label, points = []) {
  const text = Array.isArray(points) && points.length ? points.slice(0, 3).join('、') : '暂无';
  return `<div><b>${label}：</b>${escapeHtml(text)}</div>`;
}

function renderError(message) {
  els.servicePill.textContent = '异常';
  els.servicePill.className = 'pill bad';
  els.currentResult.className = 'empty';
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
