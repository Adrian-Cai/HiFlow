const DEFAULT_SETTINGS = {
  localServiceUrl: 'http://127.0.0.1:8787',
  selectedResumeId: 'resume_001',
  threshold: 90,
  scanLimit: 8,
  autoSendGreeting: false
};

const STORAGE_KEYS = {
  settings: 'hiflow.settings',
  currentResult: 'hiflow.currentResult',
  scanResults: 'hiflow.scanResults',
  queue: 'hiflow.queue',
  logs: 'hiflow.logs',
  pageState: 'hiflow.pageState'
};

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get(STORAGE_KEYS.settings).then(stored => {
    if (!stored[STORAGE_KEYS.settings]) {
      chrome.storage.local.set({ [STORAGE_KEYS.settings]: DEFAULT_SETTINGS });
    }
  });
});

chrome.action.onClicked.addListener(async tab => {
  if (!tab?.id) return;

  try {
    await chrome.tabs.sendMessage(tab.id, { type: 'HIFLOW_TOGGLE_FLOATING_PANEL' });
  } catch (error) {
    await appendLog('当前页面暂未注入 HiFlow 悬浮面板，请打开 BOSS 岗位或 chat 页面');
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  handleMessage(message, sender)
    .then(sendResponse)
    .catch(error => {
      console.warn('[HiFlow] message failed:', error);
      sendResponse({ ok: false, error: error.message || 'Unknown error' });
    });
  return true;
});

async function handleMessage(message, sender) {
  if (!message || !message.type) return { ok: false, error: 'Missing message type' };

  if (message.type === 'HIFLOW_PAGE_READY') {
    await savePageState(message.payload || {});
    return { ok: true };
  }

  if (message.type === 'HIFLOW_SCAN_PROGRESS') {
    await appendLog(`扫描中 ${message.payload?.index}/${message.payload?.total}: ${message.payload?.title || ''}`);
    return { ok: true };
  }

  if (message.type === 'HIFLOW_GET_STATE') return getState();
  if (message.type === 'HIFLOW_UPDATE_SETTINGS') return updateSettings(message.payload || {});
  if (message.type === 'HIFLOW_SAVE_RESUME') return saveResume(message.payload || {});
  if (message.type === 'HIFLOW_REFRESH_RESUMES') return refreshResumes();
  if (message.type === 'HIFLOW_ANALYZE_CURRENT') return analyzeCurrentJob();
  if (message.type === 'HIFLOW_SCAN_VISIBLE') return scanVisibleJobs();
  if (message.type === 'HIFLOW_ADD_CURRENT_TO_QUEUE') return addCurrentToQueue();
  if (message.type === 'HIFLOW_ADD_SCAN_RECOMMENDED') return addScanRecommendedToQueue();
  if (message.type === 'HIFLOW_SCAN_AND_PREPARE_GREETING') return scanAndPrepareGreeting();
  if (message.type === 'HIFLOW_REFRESH_CHAT') return refreshChatState();
  if (message.type === 'HIFLOW_CLEAR_LOGS') return clearLogs();

  return { ok: false, error: `Unsupported message type: ${message.type}` };
}

async function getState() {
  const stored = await chrome.storage.local.get(Object.values(STORAGE_KEYS));
  const settings = { ...DEFAULT_SETTINGS, ...(stored[STORAGE_KEYS.settings] || {}) };

  return {
    ok: true,
    settings,
    currentResult: stored[STORAGE_KEYS.currentResult] || null,
    scanResults: stored[STORAGE_KEYS.scanResults] || [],
    queue: stored[STORAGE_KEYS.queue] || [],
    logs: stored[STORAGE_KEYS.logs] || [],
    pageState: stored[STORAGE_KEYS.pageState] || null
  };
}

async function updateSettings(nextSettings) {
  const state = await getState();
  const settings = {
    ...state.settings,
    ...nextSettings,
    threshold: Number(nextSettings.threshold || state.settings.threshold || DEFAULT_SETTINGS.threshold),
    scanLimit: Number(nextSettings.scanLimit || state.settings.scanLimit || DEFAULT_SETTINGS.scanLimit),
    autoSendGreeting: Boolean(nextSettings.autoSendGreeting)
  };

  await chrome.storage.local.set({ [STORAGE_KEYS.settings]: settings });
  await appendLog('设置已保存');
  return getState();
}

async function saveResume(resume) {
  const state = await getState();
  const settings = state.settings;
  const baseUrl = String(settings.localServiceUrl || DEFAULT_SETTINGS.localServiceUrl).replace(/\/+$/, '');
  const resumeId = String(resume.id || settings.selectedResumeId || DEFAULT_SETTINGS.selectedResumeId).trim();

  if (!resumeId) throw new Error('简历 ID 不能为空');

  const payload = {
    id: resumeId,
    name: String(resume.name || resumeId).trim(),
    summary: String(resume.summary || '').trim(),
    target_titles: splitLines(resume.targetTitles),
    skills: splitLines(resume.skills),
    exclude_keywords: splitLines(resume.excludeKeywords)
  };

  const response = await fetch(`${baseUrl}/resumes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const message = await readErrorMessage(response);
    throw new Error(message || `保存简历画像失败：${response.status}`);
  }

  await chrome.storage.local.set({
    [STORAGE_KEYS.settings]: {
      ...settings,
      selectedResumeId: resumeId
    }
  });
  await appendLog(`简历画像已保存：${payload.name}`);
  return refreshResumes();
}

async function refreshResumes() {
  const state = await getState();
  const baseUrl = String(state.settings.localServiceUrl || DEFAULT_SETTINGS.localServiceUrl).replace(/\/+$/, '');
  const response = await fetch(`${baseUrl}/resumes`);

  if (!response.ok) {
    const message = await readErrorMessage(response);
    throw new Error(message || `读取简历画像失败：${response.status}`);
  }

  const data = await response.json();
  return {
    ...(await getState()),
    resumes: data.resumes || []
  };
}

async function analyzeCurrentJob() {
  const tab = await getActiveTab();
  const collected = await sendTabMessage(tab.id, { type: 'HIFLOW_COLLECT_CURRENT_JOB' });

  if (!collected?.ok || !collected.job?.jobText) {
    throw new Error(collected?.error || '当前标签页没有识别到岗位详情');
  }

  const result = await matchJob(collected.job);
  await chrome.storage.local.set({ [STORAGE_KEYS.currentResult]: result });
  await appendLog(`当前岗位评分完成: ${result.jobMeta.title || '未识别'} ${result.score}%`);
  return getState();
}

async function scanVisibleJobs() {
  const tab = await getActiveTab();
  const state = await getState();
  const limit = Number(state.settings.scanLimit || DEFAULT_SETTINGS.scanLimit);
  const collected = await sendTabMessage(tab.id, { type: 'HIFLOW_SCAN_VISIBLE_JOBS', limit });

  if (!collected?.ok) {
    throw new Error(collected?.error || '扫描当前可见岗位失败');
  }

  const results = [];
  for (const job of collected.jobs || []) {
    const result = await matchJob(job);
    results.push(result);
    await appendLog(`扫描评分: ${result.jobMeta.title || '未识别'} ${result.score}% ${result.decision}`);
  }

  await chrome.storage.local.set({
    [STORAGE_KEYS.scanResults]: results,
    [STORAGE_KEYS.currentResult]: results[0] || null
  });

  if (collected.skipped?.length) {
    await appendLog(`本次跳过 ${collected.skipped.length} 个未同步或无详情岗位`);
  }

  return getState();
}

async function addCurrentToQueue() {
  const state = await getState();
  if (!state.currentResult) throw new Error('当前没有可加入队列的匹配结果');
  const added = await addJobsToQueue([state.currentResult]);
  await appendLog(`当前岗位加入队列: ${added} 个`);
  return getState();
}

async function addScanRecommendedToQueue() {
  const state = await getState();
  const recommended = getRecommendedResults(state);

  const added = await addJobsToQueue(recommended);
  await appendLog(`扫描结果加入队列: ${added}/${recommended.length} 个`);
  return getState();
}

async function scanAndPrepareGreeting() {
  await scanVisibleJobs();

  const state = await getState();
  const recommended = getRecommendedResults(state);
  const tab = await getActiveTab();

  if (!recommended.length) {
    await appendLog(`没有达到阈值 ${state.settings.threshold || DEFAULT_SETTINGS.threshold}% 的岗位`);
    return getState();
  }

  await upsertQueueJobs(recommended, 'PENDING_APPLY');

  const actionPayload = recommended.map(result => ({
    id: result.id,
    jobMeta: result.jobMeta || {},
    firstMessage: result.suggestedFirstMessage || '您好，我对这个岗位比较感兴趣，方便进一步沟通吗？'
  }));

  const applyResult = await sendTabMessage(tab.id, {
    type: 'HIFLOW_PREPARE_GREETING_FOR_JOBS',
    jobs: actionPayload,
    autoSend: Boolean(state.settings.autoSendGreeting)
  });

  if (!applyResult?.ok) {
    throw new Error(applyResult?.error || '准备打招呼失败');
  }

  await updateQueueWithActions(applyResult.actions || []);

  const doneCount = (applyResult.actions || [])
    .filter(action => action.status === 'GREETING_FILLED' || action.status === 'GREETING_SENT')
    .length;
  const suffix = state.settings.autoSendGreeting ? '已自动点击发送' : '最终发送需人工确认';
  await appendLog(`打招呼流程完成：${doneCount}/${recommended.length} 个，${suffix}`);

  return getState();
}

async function refreshChatState() {
  const tab = await getActiveTab();
  const collected = await sendTabMessage(tab.id, { type: 'HIFLOW_COLLECT_CHAT_STATE' });
  if (!collected?.ok) throw new Error(collected?.error || '当前标签页不是可识别的 chat 页面');
  await savePageState(collected.chat || {});
  await appendLog(`chat 页面已刷新: ${collected.chat?.contact || collected.chat?.title || '未识别会话'}`);
  return getState();
}

async function clearLogs() {
  await chrome.storage.local.set({ [STORAGE_KEYS.logs]: [] });
  return getState();
}

async function matchJob(job) {
  const state = await getState();
  const settings = state.settings;
  const baseUrl = String(settings.localServiceUrl || DEFAULT_SETTINGS.localServiceUrl).replace(/\/+$/, '');

  const payload = {
    resume_id: settings.selectedResumeId || DEFAULT_SETTINGS.selectedResumeId,
    jd_text: job.jobText || '',
    source: 'boss',
    job_meta: job.jobMeta || {}
  };

  const response = await fetch(`${baseUrl}/match`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const message = await readErrorMessage(response);
    throw new Error(message || `本地匹配服务返回 ${response.status}`);
  }

  const data = await response.json();
  return normalizeMatchResult(data, job);
}

function normalizeMatchResult(data, job) {
  return {
    id: makeJobId(job.jobMeta || {}),
    jobMeta: job.jobMeta || {},
    score: Number(data.score || 0),
    decision: String(data.decision || '').toUpperCase() === 'RECOMMEND' ? 'RECOMMEND' : 'PASS',
    matchedPoints: data.matched_points || data.matchedPoints || [],
    missingPoints: data.missing_points || data.missingPoints || [],
    riskPoints: data.risk_points || data.riskPoints || [],
    suggestedFirstMessage: data.suggested_first_message || data.suggestedFirstMessage || '',
    suggestedSecondMessage: data.suggested_second_message || data.suggestedSecondMessage || '',
    detail: data.detail || {},
    raw: data,
    createdAt: new Date().toISOString()
  };
}

async function addJobsToQueue(jobs) {
  const state = await getState();
  const queue = [...state.queue];
  let added = 0;

  jobs.forEach(job => {
    const id = job.id || makeJobId(job.jobMeta || {});
    if (!id || queue.some(item => item.id === id)) return;

    queue.push({
      id,
      status: 'PENDING_APPLY',
      jobMeta: job.jobMeta || {},
      score: job.score || 0,
      decision: job.decision || 'PASS',
      matchedPoints: job.matchedPoints || [],
      missingPoints: job.missingPoints || [],
      riskPoints: job.riskPoints || [],
      firstMessage: job.suggestedFirstMessage || '',
      secondMessage: job.suggestedSecondMessage || '',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString()
    });
    added++;
  });

  await chrome.storage.local.set({ [STORAGE_KEYS.queue]: queue });
  return added;
}

async function upsertQueueJobs(jobs, status) {
  const state = await getState();
  const queue = [...state.queue];

  jobs.forEach(job => {
    const id = job.id || makeJobId(job.jobMeta || {});
    if (!id) return;

    const existing = queue.find(item => item.id === id);
    if (existing) {
      existing.status = status;
      existing.updatedAt = new Date().toISOString();
      return;
    }

    queue.push({
      id,
      status,
      jobMeta: job.jobMeta || {},
      score: job.score || 0,
      decision: job.decision || 'PASS',
      matchedPoints: job.matchedPoints || [],
      missingPoints: job.missingPoints || [],
      riskPoints: job.riskPoints || [],
      firstMessage: job.suggestedFirstMessage || '',
      secondMessage: job.suggestedSecondMessage || '',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString()
    });
  });

  await chrome.storage.local.set({ [STORAGE_KEYS.queue]: queue });
}

async function updateQueueWithActions(actions) {
  const state = await getState();
  const queue = [...state.queue];
  const statusMap = {
    GREETING_FILLED: 'PENDING_SEND_CONFIRM',
    GREETING_SENT: 'PENDING_SECOND',
    COMMUNICATE_OPENED_NO_INPUT: 'NEED_MANUAL_INPUT',
    SEND_BUTTON_NOT_FOUND: 'NEED_MANUAL_SEND',
    COMMUNICATE_BUTTON_NOT_FOUND: 'APPLY_FAILED',
    DETAIL_NOT_SYNCED: 'APPLY_FAILED',
    CARD_NOT_FOUND: 'APPLY_FAILED'
  };

  actions.forEach(action => {
    const item = queue.find(job => job.id === action.id);
    if (!item) return;

    item.status = statusMap[action.status] || action.status || item.status;
    item.lastActionMessage = action.message || '';
    item.updatedAt = new Date().toISOString();
  });

  await chrome.storage.local.set({ [STORAGE_KEYS.queue]: queue });

  for (const action of actions) {
    await appendLog(`${action.title || '岗位'}：${action.message || action.status}`);
  }
}

function getRecommendedResults(state) {
  const threshold = Number(state.settings?.threshold || DEFAULT_SETTINGS.threshold);
  return (state.scanResults || []).filter(result => {
    return result.score >= threshold;
  });
}

function splitLines(value) {
  return String(value || '')
    .split(/[\n,，、]/)
    .map(item => item.trim())
    .filter(Boolean);
}

function makeJobId(jobMeta) {
  return [
    jobMeta.company || '',
    jobMeta.title || '',
    jobMeta.salary || '',
    jobMeta.location || '',
    jobMeta.link || ''
  ].join('|');
}

async function savePageState(pageState) {
  await chrome.storage.local.set({
    [STORAGE_KEYS.pageState]: {
      ...pageState,
      updatedAt: new Date().toISOString()
    }
  });
}

async function appendLog(message) {
  const stored = await chrome.storage.local.get(STORAGE_KEYS.logs);
  const logs = stored[STORAGE_KEYS.logs] || [];
  logs.unshift({
    message,
    at: new Date().toISOString()
  });
  await chrome.storage.local.set({ [STORAGE_KEYS.logs]: logs.slice(0, 80) });
}

async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tabs[0]?.id) throw new Error('没有找到当前活动标签页');
  return tabs[0];
}

function sendTabMessage(tabId, message) {
  return chrome.tabs.sendMessage(tabId, message);
}

async function readErrorMessage(response) {
  try {
    const data = await response.json();
    return data?.error?.message || data?.message || '';
  } catch (error) {
    return '';
  }
}
