// ==UserScript==
// @name         BOSS直聘岗位匹配与半自动打招呼助手
// @namespace    https://zhipin.com/
// @version      0.1.0
// @description  在BOSS直聘岗位列表页读取岗位JD，按个人配置计算匹配度，高分岗位辅助打招呼。不绕过验证码、不自动批量发送。
// @match        https://www.zhipin.com/web/geek/jobs*
// @match        https://www.zhipin.com/web/geek/job*
// @match        https://www.zhipin.com/web/geek/chat*
// @grant        GM_addStyle
// @grant        GM_getValue
// @grant        GM_setValue
// ==/UserScript==

(function () {
  'use strict';

  const STORE_KEY = 'boss_match_profiles_v1';
  const ACTIVE_KEY = 'boss_match_active_profile_v1';
  const SCAN_BATCH_LIMIT = 15;
  const SCANNED_JOB_KEY = 'boss_scanned_job_ids_v1';
  const QUEUE_KEY = 'boss_apply_queue_v2';
  const FIRST_TEXT = '您好，我对这份工作非常感兴趣，希望可以有机会与您进一步沟通';
  const SECOND_TEXT = '您好，我是蔡金伟，6年测试开发经验，经历过美团/字节/快手高频迭代业务质量保障。擅长自动化、性能压测、CI/CD和AI测试提效，能从业务测试推进到质量平台建设。若岗位需要复合型测试开发人才，期待进一步沟通';
  const CHAT_URL = 'https://www.zhipin.com/web/geek/chat?ka=header-message';

  const defaultProfile = {
    name: 'AI测试/测试开发',
    targetTitles: '测试工程师,测试开发工程师,自动化测试,AI测试,质量工程师,测试平台,QA,Software QA,Test Engineer',
    keywords: '软件测试,测试用例,测试计划,需求分析,缺陷管理,接口测试,自动化测试,UI自动化,Playwright,Selenium,Cypress,Postman,JMeter,k6,pytest,Python,Java,SQL,Linux,Git,Jenkins,CI/CD,Allure,测试平台,代码Diff,质量工程,AI测试,大模型,Prompt',
    excludeKeywords: '销售,电话销售,客服,地推,培训贷,无薪,保险,直播,主播,外包驻场,纯外包,996,单休',
    threshold: 83,
    greetTemplate: FIRST_TEXT
  };

  let scanning = false;
  let lastResult = null;

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  function getProfiles() {
    const raw = GM_getValue(STORE_KEY, '');
    if (!raw) return [defaultProfile];
    try {
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) && parsed.length ? parsed : [defaultProfile];
    } catch (e) {
      return [defaultProfile];
    }
  }

  function saveProfiles(profiles) {
    GM_setValue(STORE_KEY, JSON.stringify(profiles));
  }


  function getScannedJobIds() {
    try {
      const raw = GM_getValue(SCANNED_JOB_KEY, '[]');
      const parsed = JSON.parse(raw);
      return new Set(Array.isArray(parsed) ? parsed : []);
    } catch (e) {
      return new Set();
    }
  }

  function saveScannedJobIds(set) {
    GM_setValue(SCANNED_JOB_KEY, JSON.stringify(Array.from(set)));
  }


  function getQueue() {
    try {
      const parsed = JSON.parse(GM_getValue(QUEUE_KEY, '[]'));
      return Array.isArray(parsed) ? parsed : [];
    } catch (e) {
      return [];
    }
  }

  function saveQueue(queue) {
    GM_setValue(QUEUE_KEY, JSON.stringify(queue));
  }

  function makeJobId(job) {
    return [
      job.company || '',
      job.title || '',
      job.salary || '',
      job.location || ''
    ].join('|');
  }

  function addJobToApplyQueue(job) {
    const queue = getQueue();
    const id = job.id || makeJobId(job);

    if (queue.some(item => item.id === id)) return false;

    queue.push({
      id,
      title: job.title || '',
      company: job.company || '',
      salary: job.salary || '',
      location: job.location || '',
      score: job.score || 0,
      matchedKeywords: job.matchedKeywords || [],
      status: 'pending_first',
      firstText: job.firstText || FIRST_TEXT,
      secondText: job.secondText || SECOND_TEXT,
      createdAt: Date.now(),
      updatedAt: Date.now()
    });

    saveQueue(queue);
    return true;
  }

  function updateQueueStatus(id, status, extra = {}) {
    const next = getQueue().map(item => {
      if (item.id !== id) return item;
      return {
        ...item,
        ...extra,
        status,
        updatedAt: Date.now()
      };
    });

    saveQueue(next);
  }

  function getPendingFirstJobs() {
    return getQueue().filter(item => item.status === 'pending_first');
  }

  function getPendingSecondJobs() {
    return getQueue().filter(item => item.status === 'pending_second');
  }

  function formatQueueSummary(queue = getQueue()) {
    const groups = queue.reduce((acc, item) => {
      acc[item.status] = (acc[item.status] || 0) + 1;
      return acc;
    }, {});

    return [
      `总数：${queue.length}`,
      `待第一条：${groups.pending_first || 0}`,
      `待第二条：${groups.pending_second || 0}`,
      `已完成：${groups.done || 0}`,
      `失败：${(groups.first_failed || 0) + (groups.second_failed || 0)}`,
      `跳过：${groups.skipped || 0}`
    ].join(' / ');
  }

  function clearScannedJobIds() {
    GM_setValue(SCANNED_JOB_KEY, '[]');
    const status = document.querySelector('#bh-status');
    if (status) status.textContent = '已清空扫描记录';
    alert('已清空扫描记录。');
  }

  function getActiveProfile() {
    const profiles = getProfiles();
    const activeName = GM_getValue(ACTIVE_KEY, profiles[0].name);
    return profiles.find(p => p.name === activeName) || profiles[0];
  }

  function setActiveProfileName(name) {
    GM_setValue(ACTIVE_KEY, name);
  }

  function normalizeText(text) {
    return String(text || '')
      .replace(/\s+/g, ' ')
      .replace(/[，。；：、]/g, ',')
      .trim()
      .toLowerCase();
  }

  function splitWords(str) {
    return String(str || '')
      .split(/[,，、\n\r;；|/]+/)
      .map(s => s.trim())
      .filter(Boolean);
  }

  function isVisible(el) {
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
  }


  function extractJobCardMeta(card) {
    const text = card?.innerText || '';
    const lines = text
      .split('\n')
      .map(x => x.trim())
      .filter(Boolean);

    function pickBySelector(selectors) {
      for (const selector of selectors) {
        const el = card?.querySelector(selector);
        const value = (el?.innerText || '').trim();
        if (value) return value;
      }
      return '';
    }

    const title =
      pickBySelector([
        '.job-name',
        '.job-title',
        '[class*="job-name"]',
        '[class*="job-title"]',
        '.name'
      ]) || lines[0] || '';

    const salary =
      lines.find(x => /\d+\s*-\s*\d+\s*[Kk]|\d+\s*[Kk]/.test(x)) || '';

    const company =
      pickBySelector([
        '.company-name',
        '[class*="company-name"]',
        '.company-text',
        '[class*="company"]'
      ]) ||
      lines.find(x => {
        return !x.includes(title) &&
          !x.includes(salary) &&
          x.length >= 2 &&
          x.length <= 30 &&
          !/本科|大专|硕士|经验|年|上海|北京|深圳|广州|杭州|JMeter|Postman|Python|测试/.test(x);
      }) || '';

    const location =
      lines.find(x => /上海|北京|深圳|广州|杭州|成都|武汉|南京|苏州|重庆|西安/.test(x)) || '';

    const tags = lines.filter(x => {
      return /本科|大专|硕士|经验|年|Python|Java|JMeter|Postman|Selenium|Playwright|自动化|接口|性能|测试/.test(x);
    });

    const link =
      card?.querySelector('a[href*="/job_detail/"]')?.href ||
      card?.closest('a[href*="/job_detail/"]')?.href ||
      '';

    return {
      title,
      company,
      salary,
      location,
      tags,
      link,
      rawText: text
    };
  }

  function getJobStableId(cardMeta) {
    if (cardMeta.link) {
      const match = cardMeta.link.match(/job_detail\/([^?/.]+)/);
      if (match) return match[1];
      return cardMeta.link;
    }

    return [
      cardMeta.company || '',
      cardMeta.title || '',
      cardMeta.salary || '',
      cardMeta.location || ''
    ].join('|');
  }

  function getJobCards() {
    const selectors = [
      '.job-card-wrapper',
      '.job-card-body',
      '.job-list-box .job-card-wrapper',
      '.search-job-result .job-card-wrapper',
      'li[class*="job-card"]',
      'div[class*="job-card"]'
    ];

    const set = new Set();

    selectors.forEach(sel => {
      document.querySelectorAll(sel).forEach(el => {
        if (isVisible(el)) set.add(el);
      });
    });

    return Array.from(set).filter(el => {
      const txt = normalizeText(el.innerText);
      return txt.length > 20 && /k|薪|经验|学历|公司|boss|hr|招聘|测试|开发|工程|产品|运营/.test(txt);
    });
  }

  function getCurrentCardText() {
    const activeSelectors = [
      '.job-card-wrapper.active',
      '.job-card-wrapper.selected',
      '.job-card-wrapper.cur',
      '.job-card-wrapper:hover',
      '.job-card-body.active',
      '.job-card-body.selected'
    ];

    for (const sel of activeSelectors) {
      const el = document.querySelector(sel);
      if (el && isVisible(el)) return el.innerText || '';
    }

    return '';
  }

function getRightDetailRoot() {
  const prioritySelectors = [
    '.job-detail-box',
    '.job-detail-container',
    '.job-detail',
    '.job-primary.detail-box',
    '.job-sec',
    '.job-detail-section',
    '[class*="job-detail"]'
  ];

  for (const selector of prioritySelectors) {
    const nodes = Array.from(document.querySelectorAll(selector));

    const hit = nodes.find(el => {
      if (!isVisible(el)) return false;
      if (el.closest('#boss-helper-panel')) return false;

      const rect = el.getBoundingClientRect();
      const text = el.innerText || '';

      return (
        rect.left > window.innerWidth * 0.35 &&
        rect.width > 300 &&
        rect.height > 200 &&
        text.length > 100 &&
        /职位描述|岗位职责|岗位要求|工作地址|任职要求|加分项|薪资|经验/.test(text)
      );
    });

    if (hit) return hit;
  }

  const candidates = Array.from(document.querySelectorAll('div, section, main'))
    .filter(el => {
      if (!isVisible(el)) return false;
      if (el.closest('#boss-helper-panel')) return false;

      const rect = el.getBoundingClientRect();
      const text = el.innerText || '';

      return (
        rect.left > window.innerWidth * 0.35 &&
        rect.width > 350 &&
        rect.height > 300 &&
        text.length > 150 &&
        /职位描述|岗位职责|岗位要求|工作地址|任职要求|加分项/.test(text)
      );
    })
    .map(el => {
      const text = el.innerText || '';
      let score = 0;

      if (/职位描述/.test(text)) score += 20;
      if (/岗位职责/.test(text)) score += 20;
      if (/岗位要求|任职要求/.test(text)) score += 20;
      if (/工作地址/.test(text)) score += 10;
      if (/薪资|K|k/.test(text)) score += 5;
      score += Math.min(30, text.length / 100);

      return { el, score };
    })
    .sort((a, b) => b.score - a.score);

  return candidates[0]?.el || null;
}

function getCleanTextFromElement(el) {
  if (!el) return '';

  const clone = el.cloneNode(true);

  clone.querySelectorAll('#boss-helper-panel, script, style, noscript').forEach(node => node.remove());

  return (clone.innerText || '')
    .replace(/\s+/g, ' ')
    .trim();
}

function getCurrentJobSnapshot() {
  const root = getRightDetailRoot();
  const text = getCleanTextFromElement(root);

  let title = '';
  let company = '';
  let salary = '';
  let location = '';

  if (root) {
    const titleSelectors = [
      '.job-title',
      '[class*="job-title"]',
      '.name',
      '[class*="name"]'
    ];

    for (const selector of titleSelectors) {
      const el = root.querySelector(selector);
      const value = (el?.innerText || '').trim();
      if (value && value.length <= 80 && !/收藏|沟通|职位描述|岗位职责/.test(value)) {
        title = value;
        break;
      }
    }

    const companySelectors = [
      '.company-name',
      '[class*="company-name"]',
      '.company-info .name',
      '[class*="company"] .name'
    ];

    for (const selector of companySelectors) {
      const el = root.querySelector(selector);
      const value = (el?.innerText || '').trim();
      if (value && value.length <= 60) {
        company = value;
        break;
      }
    }

    const allLines = (root.innerText || '')
      .split('\n')
      .map(x => x.trim())
      .filter(Boolean);

    salary = allLines.find(x => /\d+\s*-\s*\d+\s*K|\d+\s*-\s*\d+\s*k|\d+K|\d+k/.test(x)) || '';
    location = allLines.find(x => /上海|北京|深圳|广州|杭州|成都|武汉|南京|苏州|重庆|西安/.test(x)) || '';
  }

  return {
    root,
    title,
    company,
    salary,
    location,
    text
  };
}

function getJobDetailText() {
  const snapshot = getCurrentJobSnapshot();
  return snapshot.text || '';
}

  function extractJobTitleFromPage() {
    const selectors = [
      '.job-title',
      '.name',
      '[class*="job-title"]',
      '[class*="title"]'
    ];

    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && isVisible(el)) {
        const text = (el.innerText || '').trim();
        if (text.length > 1 && text.length < 80) return text;
      }
    }

    const cardText = getCurrentCardText();
    return cardText.split('\n').slice(0, 2).join(' ');
  }

  function calcMatch(profile, jobText) {
    const text = normalizeText(jobText);
    const targetTitles = splitWords(profile.targetTitles);
    const keywords = splitWords(profile.keywords);
    const excludeKeywords = splitWords(profile.excludeKeywords);

    const matchedTitle = targetTitles.filter(k => text.includes(k.toLowerCase()));
    const matchedKeywords = keywords.filter(k => text.includes(k.toLowerCase()));
    const hitExcludes = excludeKeywords.filter(k => text.includes(k.toLowerCase()));

    const titleScore = targetTitles.length
      ? Math.min(1, matchedTitle.length / Math.min(targetTitles.length, 3)) * 25
      : 0;

    const keywordScore = keywords.length
      ? Math.min(1, matchedKeywords.length / Math.min(keywords.length, 12)) * 55
      : 0;

    let baseScore = titleScore + keywordScore;

    if (/本科|统招本科|硕士|研究生|学历/.test(text)) baseScore += 5;
    if (/3-5年|1-3年|5-10年|经验|项目经验/.test(text)) baseScore += 5;
    if (/自动化|平台|质量|测试开发|接口|性能|ai|大模型|agent|ci\/cd|devops/.test(text)) baseScore += 10;

    if (hitExcludes.length > 0) {
      baseScore -= Math.min(35, hitExcludes.length * 15);
    }

    const score = Math.max(0, Math.min(100, Math.round(baseScore)));

    return {
      score,
      matchedTitle,
      matchedKeywords,
      hitExcludes,
      recommendation:
        score >= Number(profile.threshold || 83) && hitExcludes.length === 0
          ? '推荐沟通'
          : '暂不推荐'
    };
  }

  function buildGreeting(profile, result) {
    const matched = result.matchedKeywords.slice(0, 6).join('、') || '岗位要求';
    return String(profile.greetTemplate || defaultProfile.greetTemplate)
      .replaceAll('{matched}', matched)
      .replaceAll('{score}', String(result.score));
  }

  function findButtonByText(textList) {
    return findClickableByText(textList);
  }

  function findChatInput() {
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
      if (el && isVisible(el)) return el;
    }

    return null;
  }

  function fillInput(input, text) {
    input.focus();

    if ('value' in input) {
      input.value = text;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
    } else {
      input.innerText = text;
      input.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
    }
  }

  function findClickableByText(textList) {
    const nodes = Array.from(document.querySelectorAll('button,a,div,span'));
    const candidates = nodes.filter(el => {
      if (!isVisible(el)) return false;
      const txt = (el.innerText || '').trim();
      if (!txt) return false;
      return textList.some(t => txt.includes(t));
    });

    for (const el of candidates) {
      const clickable = el.closest('button,a,[role="button"],.btn,.button') || el;
      if (isVisible(clickable)) return clickable;
    }

    return null;
  }

  async function fillGreetingText(text) {
    await sleep(800);

    const inputSelectors = [
      'textarea',
      'input[type="text"]',
      '[contenteditable="true"]',
      '.chat-input textarea',
      '.input-area textarea',
      '[class*="input"] textarea',
      '[class*="editor"]'
    ];

    for (const sel of inputSelectors) {
      const el = document.querySelector(sel);
      if (!el || !isVisible(el)) continue;

      el.focus();

      if ('value' in el) {
        el.value = text;
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
      } else {
        el.innerText = text;
        el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
      }

      return true;
    }

    return false;
  }

  async function greetCurrentJob() {
    const profile = getActiveProfile();
    const jobText = getJobDetailText();
    const result = calcMatch(profile, jobText);
    lastResult = result;

    updateResultBox(result, getCurrentJobSnapshot());

    if (result.score < Number(profile.threshold || 83)) {
      alert(`当前匹配度 ${result.score}%，低于阈值 ${profile.threshold}%，不建议沟通。`);
      return;
    }

    if (result.hitExcludes.length > 0) {
      alert(`命中排除词：${result.hitExcludes.join('、')}。不建议沟通。`);
      return;
    }

    const btn = findClickableByText(['立即沟通', '继续沟通', '打招呼', '沟通']);
    if (!btn) {
      alert('没有找到“立即沟通/继续沟通”按钮。可能是页面结构变化，或当前岗位不可沟通。');
      return;
    }

    btn.click();

    const greetText = buildGreeting(profile, result);
    const filled = await fillGreetingText(greetText);

    if (filled) {
      alert('已打开沟通窗口并填入话术，请你人工确认后再发送。');
    } else {
      alert(`已尝试打开沟通窗口，但没有找到输入框。话术如下：\n\n${greetText}`);
    }
  }

  function analyzeCurrentJob(source = 'manual', cardMeta = {}, snapshotOverride = null) {
    const profile = getActiveProfile();
    const snapshot = snapshotOverride || getCurrentJobSnapshot();
    const jobText = snapshot.text;

    if (!jobText || jobText.length < 80) {
      const box = document.querySelector('#boss-helper-result');
      if (box) {
        box.innerHTML = `
          <div style="color:#b54708;font-weight:700;">未识别到右侧岗位详情</div>
          <div>请先点击左侧岗位卡片，等待右侧详情加载完成后再试。</div>
        `;
      }
      return;
    }

    const result = calcMatch(profile, jobText);
    lastResult = result;

    updateResultBox(result, snapshot, cardMeta);

    const status = document.querySelector('#bh-status');
    if (status) {
      status.textContent = source === 'card-click'
        ? '已根据当前点击岗位自动刷新'
        : '当前岗位分析完成';
    }
  }

  function updateResultBox(result, snapshot = {}, cardMeta = {}) {
    const box = document.querySelector('#boss-helper-result');
    if (!box) return;

    const matched = result.matchedKeywords?.slice(0, 12).join('、') || '暂无';
    const missing = result.missingKeywords?.slice(0, 8).join('、') || '暂无';
    const titles = result.matchedTitle?.join('、') || '暂无';
    const excludes = result.hitExcludes?.join('、') || '无';
    const detail = result.detail || {};

    const hasCardMeta = Boolean(cardMeta && Object.keys(cardMeta).length);
    const leftTitle = cardMeta.title || '未识别';
    const leftCompany = cardMeta.company || '';
    const leftSalary = cardMeta.salary || '';
    const leftLocation = cardMeta.location || '';

    const rightTitle = snapshot.title || '未识别';
    const rightCompany = snapshot.company || '';
    const rightSalary = snapshot.salary || '';
    const rightLocation = snapshot.location || '';
    const syncOk = hasCardMeta ? isRightDetailMatchedWithCard(snapshot, cardMeta) : true;

    box.innerHTML = `
      <div class="bh-score ${result.recommendation === '推荐沟通' ? 'ok' : 'bad'}">${result.score}%</div>
      ${hasCardMeta ? `<div><b>同步状态：</b>${syncOk ? '已同步当前卡片' : '<span style="color:#b54708;">可能未同步</span>'}</div>` : ''}

      ${hasCardMeta ? `
        <hr style="border:none;border-top:1px solid #eee;margin:8px 0;" />
        <div><b>左侧卡片：</b>${escapeHtml(leftTitle)}</div>
        <div><b>左侧公司：</b>${escapeHtml(leftCompany || '未识别')}</div>
        <div><b>左侧信息：</b>${escapeHtml([leftSalary, leftLocation].filter(Boolean).join(' / ') || '未识别')}</div>
      ` : ''}

      <hr style="border:none;border-top:1px solid #eee;margin:8px 0;" />
      <div><b>${hasCardMeta ? '右侧详情' : '当前岗位'}：</b>${escapeHtml(rightTitle)}</div>
      <div><b>${hasCardMeta ? '右侧公司' : '公司'}：</b>${escapeHtml(rightCompany || '未识别')}</div>
      <div><b>${hasCardMeta ? '右侧信息' : '岗位信息'}：</b>${escapeHtml([rightSalary, rightLocation].filter(Boolean).join(' / ') || '未识别')}</div>

      <hr style="border:none;border-top:1px solid #eee;margin:8px 0;" />
      <div><b>判断：</b>${escapeHtml(result.recommendation)}</div>
      ${detail.semanticScore !== undefined ? `<div><b>简历-JD相似度：</b>${detail.semanticScore}%</div>` : ''}
      ${detail.skillScore !== undefined ? `<div><b>技能覆盖度：</b>${detail.skillScore}%</div>` : ''}
      ${detail.titleScore !== undefined ? `<div><b>岗位方向：</b>${detail.titleScore}%</div>` : ''}
      ${detail.conditionScore !== undefined ? `<div><b>硬性条件：</b>${detail.conditionScore}%</div>` : ''}
      ${detail.experienceScore !== undefined ? `<div><b>年限匹配：</b>${detail.experienceScore}%</div>` : ''}
      <div><b>命中岗位：</b>${escapeHtml(titles)}</div>
      <div><b>匹配能力：</b>${escapeHtml(matched)}</div>
      <div><b>缺失能力：</b>${escapeHtml(missing)}</div>
      <div><b>排除词：</b>${escapeHtml(excludes)}</div>
    `;
  }

  function renderProfileOptions() {
    const profiles = getProfiles();
    const active = getActiveProfile();
    const sel = document.querySelector('#bh-profile-select');
    if (!sel) return;

    sel.innerHTML = profiles.map(p => {
      const selected = p.name === active.name ? 'selected' : '';
      return `<option value="${escapeHtml(p.name)}" ${selected}>${escapeHtml(p.name)}</option>`;
    }).join('');
  }

  function loadProfileToForm(profile) {
    document.querySelector('#bh-name').value = profile.name || '';
    document.querySelector('#bh-title').value = profile.targetTitles || '';
    document.querySelector('#bh-keywords').value = profile.keywords || '';
    document.querySelector('#bh-excludes').value = profile.excludeKeywords || '';
    document.querySelector('#bh-threshold').value = profile.threshold || 83;
    document.querySelector('#bh-greet').value = profile.greetTemplate || '';
  }

  function readProfileFromForm() {
    return {
      name: document.querySelector('#bh-name').value.trim() || '未命名配置',
      targetTitles: document.querySelector('#bh-title').value.trim(),
      keywords: document.querySelector('#bh-keywords').value.trim(),
      excludeKeywords: document.querySelector('#bh-excludes').value.trim(),
      threshold: Number(document.querySelector('#bh-threshold').value || 83),
      greetTemplate: document.querySelector('#bh-greet').value.trim()
    };
  }

  function saveCurrentProfile() {
    const p = readProfileFromForm();
    let profiles = getProfiles();
    const idx = profiles.findIndex(x => x.name === p.name);

    if (idx >= 0) {
      profiles[idx] = p;
    } else {
      profiles.push(p);
    }

    saveProfiles(profiles);
    setActiveProfileName(p.name);
    renderProfileOptions();
    alert('配置已保存。');
  }

  function deleteCurrentProfile() {
    const p = readProfileFromForm();
    let profiles = getProfiles().filter(x => x.name !== p.name);

    if (!profiles.length) profiles = [defaultProfile];

    saveProfiles(profiles);
    setActiveProfileName(profiles[0].name);
    renderProfileOptions();
    loadProfileToForm(profiles[0]);
    alert('配置已删除。');
  }

  function escapeHtml(str) {
    return String(str || '').replace(/[&<>"']/g, s => {
      return ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
      })[s];
    });
  }

  function markCard(card, result) {
    card.setAttribute('data-boss-score', result.score);

    const old = card.querySelector('.boss-helper-badge');
    if (old) old.remove();

    const badge = document.createElement('div');
    badge.className = 'boss-helper-badge';
    badge.textContent = `${result.score}% ${result.recommendation}`;

    if (result.recommendation === '推荐沟通') {
      badge.classList.add('ok');
      card.classList.add('boss-helper-card-ok');
    } else {
      badge.classList.add('bad');
      card.classList.remove('boss-helper-card-ok');
    }

    card.style.position = 'relative';
    card.appendChild(badge);
  }


  function getCurrentVisibleJobCards(limit = SCAN_BATCH_LIMIT) {
    const cards = getJobCards();

    const visibleCards = cards.filter(card => {
      if (!isVisible(card)) return false;

      const rect = card.getBoundingClientRect();
      const inViewport =
        rect.bottom > 80 &&
        rect.top < window.innerHeight - 60 &&
        rect.left < window.innerWidth * 0.45;

      return inViewport;
    });

    return visibleCards.slice(0, limit);
  }

  function simpleText(str) {
    return String(str || '')
      .replace(/\s+/g, '')
      .replace(/[（）()【】\[\]「」]/g, '')
      .toLowerCase();
  }

  function isRightDetailMatchedWithCard(snapshot = {}, cardMeta = {}) {
    const rightText = simpleText(snapshot.text || '');
    const rightTitle = simpleText(snapshot.title || '');
    const rightCompany = simpleText(snapshot.company || '');

    const cardTitle = simpleText(cardMeta.title || '');
    const cardCompany = simpleText(cardMeta.company || '');

    if (!rightText || !cardTitle) return false;

    if (cardTitle && rightText.includes(cardTitle)) return true;
    if (cardTitle.length >= 5 && rightText.includes(cardTitle.slice(0, 5))) return true;
    if (cardTitle.length >= 4 && rightTitle.includes(cardTitle.slice(0, 4))) return true;
    if (cardCompany && rightText.includes(cardCompany)) return true;
    if (cardCompany && rightCompany && rightCompany.includes(cardCompany)) return true;

    return false;
  }

  async function waitRightDetailReadyForCard(cardMeta, timeout = 7000) {
    const start = Date.now();
    let lastSnapshot = null;

    while (Date.now() - start < timeout) {
      await sleep(250);

      const snapshot = getCurrentJobSnapshot();
      lastSnapshot = snapshot;

      if (!snapshot.text || snapshot.text.length < 80) {
        continue;
      }

      if (isRightDetailMatchedWithCard(snapshot, cardMeta)) {
        return { ok: true, snapshot };
      }
    }

    return { ok: false, snapshot: lastSnapshot || getCurrentJobSnapshot() };
  }

  function addHighScoreJobsToQueue(scoredJobs = window.__bossScoredJobs || [], threshold = Number(getActiveProfile().threshold || 83)) {
    let added = 0;

    scoredJobs.forEach(job => {
      if (job.score >= threshold && (!job.hitExcludes || job.hitExcludes.length === 0)) {
        const ok = addJobToApplyQueue(job);
        if (ok) added++;
      }
    });

    refreshQueueStatus();
    alert(`已加入 ${added} 个高分岗位到投递队列。`);
  }

  function addJobToQueueIfAvailable(scoredJob) {
    return addJobToApplyQueue(scoredJob);
  }

  async function scanVisibleCards() {
    if (scanning) return;

    scanning = true;

    const profile = getActiveProfile();
    const cards = getCurrentVisibleJobCards(SCAN_BATCH_LIMIT);
    const scannedIds = getScannedJobIds();
    const status = document.querySelector('#bh-status');

    let scannedCount = 0;
    let skippedCount = 0;

    if (!cards.length) {
      alert('没有识别到当前可见岗位卡片。请确认左侧岗位列表已经加载。');
      scanning = false;
      return;
    }

    window.__bossScoredJobs = window.__bossScoredJobs || [];

    if (status) {
      status.textContent = `本次最多扫描 ${SCAN_BATCH_LIMIT} 个当前可见岗位`;
    }

    for (let i = 0; i < cards.length; i++) {
      if (!scanning) break;

      const card = cards[i];
      const cardMeta = extractJobCardMeta(card);
      const stableId = getJobStableId(cardMeta);

      if (scannedIds.has(stableId)) {
        skippedCount++;

        markCard(card, {
          score: 0,
          recommendation: '已扫过'
        });

        continue;
      }

      if (status) {
        status.textContent = `扫描当前批次：${i + 1}/${cards.length}，岗位：${cardMeta.title || '未识别'}`;
      }

      const box = document.querySelector('#boss-helper-result');
      if (box) {
        box.innerHTML = `
          <div style="font-weight:700;">正在扫描当前批次 ${i + 1}/${cards.length}</div>
          <div><b>左侧卡片：</b>${escapeHtml(cardMeta.title || '未识别')}</div>
          <div><b>公司：</b>${escapeHtml(cardMeta.company || '未识别')}</div>
          <div><b>薪资/地点：</b>${escapeHtml([cardMeta.salary, cardMeta.location].filter(Boolean).join(' / ') || '未识别')}</div>
          <div style="margin-top:6px;color:#666;">等待右侧岗位详情同步...</div>
        `;
      }

      card.scrollIntoView({ block: 'center', behavior: 'smooth' });
      await sleep(400);
      card.click();

      const waitResult = await waitRightDetailReadyForCard(cardMeta, 7000);
      const snapshot = waitResult.snapshot;

      if (!waitResult.ok) {
        console.warn('右侧详情未同步当前卡片，跳过：', cardMeta, snapshot);

        markCard(card, {
          score: 0,
          recommendation: '未同步'
        });

        continue;
      }

      const jobText = snapshot.text;

      if (!jobText || jobText.length < 80) {
        markCard(card, {
          score: 0,
          recommendation: '无详情'
        });

        scannedIds.add(stableId);
        saveScannedJobIds(scannedIds);

        continue;
      }

      const result = calcMatch(profile, jobText);

      const scoredJob = {
        id: stableId,
        title: snapshot.title || cardMeta.title || '',
        company: snapshot.company || cardMeta.company || '',
        salary: snapshot.salary || cardMeta.salary || '',
        location: snapshot.location || cardMeta.location || '',
        score: result.score,
        recommendation: result.recommendation,
        matchedKeywords: result.matchedKeywords || [],
        missingKeywords: result.missingKeywords || [],
        hitExcludes: result.hitExcludes || [],
        cardMeta,
        snapshot
      };

      window.__bossScoredJobs.push(scoredJob);

      markCard(card, result);
      updateResultBox(result, snapshot, cardMeta);

      scannedIds.add(stableId);
      saveScannedJobIds(scannedIds);

      scannedCount++;

      await sleep(1200 + Math.floor(Math.random() * 800));
    }

    if (status) {
      status.textContent = scanning
        ? `当前批次完成：新扫 ${scannedCount} 个，跳过重复 ${skippedCount} 个。请点击“加入高分岗位队列”沉淀结果`
        : '已停止';
    }

    scanning = false;
  }

  function stopScan() {
    scanning = false;
    const status = document.querySelector('#bh-status');
    if (status) status.textContent = '已请求停止';
  }

  const JOB_CARD_SELECTOR = [
    '.job-card-wrapper',
    '.job-card-body',
    '.search-job-result .job-card-wrapper',
    '.job-list-box .job-card-wrapper',
    'li[class*="job-card"]',
    'div[class*="job-card"]'
  ].join(',');

  let bossAutoAnalyzeSeq = 0;

  function getCurrentDetailFingerprint() {
    const snapshot = getCurrentJobSnapshot();
    const raw = [
      snapshot.title || '',
      snapshot.salary || '',
      snapshot.location || '',
      (snapshot.text || '').slice(0, 500)
    ].join('|');

    return normalizeText(raw).slice(0, 800);
  }

  async function waitForDetailChange(beforeFingerprint, timeout = 5000) {
    const start = Date.now();

    while (Date.now() - start < timeout) {
      await sleep(250);

      const now = getCurrentDetailFingerprint();

      if (now && now !== beforeFingerprint) {
        return true;
      }
    }

    return false;
  }

  function bindJobCardClickAutoAnalyze() {
    if (window.__bossJobCardClickAutoAnalyzeBound) return;
    window.__bossJobCardClickAutoAnalyzeBound = true;

    document.addEventListener('click', async function (event) {
      const panel = document.querySelector('#boss-helper-panel');

      if (panel && panel.contains(event.target)) return;

      const card = event.target.closest(JOB_CARD_SELECTOR);
      if (!card) return;

      if (typeof scanning !== 'undefined' && scanning) return;

      const cardMeta = extractJobCardMeta(card);
      const currentSeq = ++bossAutoAnalyzeSeq;

      const status = document.querySelector('#bh-status');
      if (status) {
        status.textContent = `检测到岗位卡片点击，等待右侧详情刷新：${cardMeta.title || '未识别岗位'}`;
      }

      setTimeout(async () => {
        const waitResult = await waitRightDetailReadyForCard(cardMeta, 6000);

        if (currentSeq !== bossAutoAnalyzeSeq) return;

        if (!waitResult.ok) {
          if (status) {
            status.textContent = '右侧详情未同步当前点击岗位，请稍后重试';
          }

          const box = document.querySelector('#boss-helper-result');
          if (box) {
            box.innerHTML = `
              <div style="color:#b54708;font-weight:700;">右侧详情可能未同步</div>
              <div><b>左侧卡片：</b>${escapeHtml(cardMeta.title || '未识别')}</div>
              <div><b>公司：</b>${escapeHtml(cardMeta.company || '未识别')}</div>
              <div>已避免使用上一条岗位详情重新评分，请等待页面加载完成后再试。</div>
            `;
          }

          return;
        }

        analyzeCurrentJob('card-click', cardMeta, waitResult.snapshot);
      }, 0);

    }, true);
  }


  async function sendFirstGreetingForCurrentJob(job) {
    const communicateBtn = findButtonByText(['立即沟通', '继续沟通', '打招呼', '感兴趣', '沟通']);

    if (!communicateBtn) {
      alert('没有找到立即沟通按钮，可能页面结构变化，或该岗位暂时不能沟通。');
      return false;
    }

    communicateBtn.click();
    await sleep(1000);

    const input = findChatInput();
    if (!input) {
      alert('已点击沟通按钮，但没有识别到输入框。请确认第一条是否已发送。');
      return false;
    }

    fillInput(input, job.firstText || FIRST_TEXT);
    await sleep(500);

    const sendBtn = findButtonByText(['发送']);
    if (!sendBtn) {
      alert('已填入第一条消息，但没有找到发送按钮，请手动发送。');
      return false;
    }

    sendBtn.click();
    return true;
  }

  async function processFirstGreetingQueue() {
    const queue = getPendingFirstJobs();

    if (!queue.length) {
      alert('没有待发送第一条的岗位。');
      return;
    }

    for (const job of queue) {
      const confirmed = confirm(`准备发送第一条：\n\n${job.company}\n${job.title}\n匹配分：${job.score}\n\n请确认当前右侧详情就是该岗位，是否继续？`);

      if (!confirmed) {
        updateQueueStatus(job.id, 'skipped');
        refreshQueueStatus();
        continue;
      }

      const ok = await sendFirstGreetingForCurrentJob(job);
      updateQueueStatus(job.id, ok ? 'pending_second' : 'first_failed', ok ? { firstSentAt: Date.now() } : {});
      refreshQueueStatus();

      await sleep(3000 + Math.random() * 3000);
    }

    alert('第一条处理完成。接下来进入聊天页发送第二条。');
  }

  async function sendSecondMessageForCurrentChat() {
    const queue = getPendingSecondJobs();

    if (!queue.length) {
      alert('没有待发送第二条的岗位。');
      return;
    }

    const job = queue[0];
    const confirmed = confirm(`准备在当前聊天窗口发送第二条：\n\n${job.company}\n${job.title}\n匹配分：${job.score}\n\n请确认当前聊天窗口就是这个HR，再继续。`);
    if (!confirmed) return;

    const input = findChatInput();
    if (!input) {
      alert('没有找到聊天输入框。请先打开一个HR聊天窗口。');
      return;
    }

    fillInput(input, job.secondText || SECOND_TEXT);
    await sleep(500);

    const sendBtn = findButtonByText(['发送']);
    if (!sendBtn) {
      alert('已填入第二条消息，但没有找到发送按钮，请手动发送。');
      return;
    }

    sendBtn.click();
    updateQueueStatus(job.id, 'done', { secondSentAt: Date.now() });
    refreshQueueStatus();
    alert('第二条已发送，并已标记为完成。');
  }

  function skipCurrentSecondJob() {
    const job = getPendingSecondJobs()[0];
    if (!job) return alert('没有待发送第二条的岗位。');
    updateQueueStatus(job.id, 'skipped');
    refreshQueueStatus();
  }

  function markCurrentSecondDone() {
    const job = getPendingSecondJobs()[0];
    if (!job) return alert('没有待发送第二条的岗位。');
    updateQueueStatus(job.id, 'done', { secondSentAt: Date.now(), manualDone: true });
    refreshQueueStatus();
  }

  function viewApplyQueue(statusFilter = '') {
    const queue = statusFilter ? getQueue().filter(item => item.status === statusFilter) : getQueue();
    const lines = queue.slice(0, 20).map((item, index) => `${index + 1}. [${item.status}] ${item.company} / ${item.title} / ${item.score}分`);
    alert(`${formatQueueSummary(getQueue())}\n\n${lines.join('\n') || '暂无队列数据'}`);
  }

  function refreshQueueStatus() {
    const status = document.querySelector('#bh-status');
    if (status) status.textContent = formatQueueSummary();
  }

  function createPanel() {
    if (document.querySelector('#boss-helper-panel')) return;

    const panel = document.createElement('div');
    panel.id = 'boss-helper-panel';
    panel.innerHTML = `
      <div class="bh-head">
        <b>BOSS匹配助手</b>
        <button id="bh-toggle">收起</button>
      </div>

      <div id="bh-body">
        <label>选择配置</label>
        <select id="bh-profile-select"></select>

        <label>配置名称</label>
        <input id="bh-name" />

        <label>目标岗位词</label>
        <textarea id="bh-title" rows="2"></textarea>

        <label>核心匹配关键词</label>
        <textarea id="bh-keywords" rows="4"></textarea>

        <label>排除词</label>
        <textarea id="bh-excludes" rows="2"></textarea>

        <label>匹配阈值</label>
        <input id="bh-threshold" type="number" min="0" max="100" />

        <label>打招呼话术，可用 {matched} 和 {score}</label>
        <textarea id="bh-greet" rows="3"></textarea>

        <div class="bh-row">
          <button id="bh-save">保存配置</button>
          <button id="bh-delete">删除配置</button>
        </div>

        <div class="bh-row">
          <button id="bh-analyze">分析当前岗位</button>
          <button id="bh-greet-btn">打招呼/填话术</button>
        </div>

        <div class="bh-row">
          <button id="bh-scan">扫描当前批次</button>
          <button id="bh-stop">停止</button>
        </div>

        <div class="bh-row">
          <button id="bh-add-high">加入高分岗位队列</button>
          <button id="bh-process-first">发送当前岗位第一条</button>
        </div>

        <div class="bh-row">
          <button id="bh-view-queue">查看投递队列</button>
          <button id="bh-open-chat">打开聊天页</button>
        </div>

        <div class="bh-row">
          <button id="bh-clear-scan">清空扫描记录</button>
        </div>

        <div id="bh-status">待操作</div>
        <div id="boss-helper-result">
          <div class="bh-empty">点击左侧岗位卡片后，点“分析当前岗位”。</div>
        </div>
      </div>
    `;

    document.body.appendChild(panel);

    renderProfileOptions();
    loadProfileToForm(getActiveProfile());

    document.querySelector('#bh-profile-select').addEventListener('change', e => {
      const name = e.target.value;
      setActiveProfileName(name);
      const p = getProfiles().find(x => x.name === name);
      if (p) loadProfileToForm(p);
    });

    document.querySelector('#bh-save').addEventListener('click', saveCurrentProfile);
    document.querySelector('#bh-delete').addEventListener('click', deleteCurrentProfile);
    document.querySelector('#bh-analyze').addEventListener('click', analyzeCurrentJob);
    document.querySelector('#bh-greet-btn').addEventListener('click', greetCurrentJob);
    document.querySelector('#bh-scan').addEventListener('click', scanVisibleCards);
    document.querySelector('#bh-stop').addEventListener('click', stopScan);
    document.querySelector('#bh-clear-scan').addEventListener('click', clearScannedJobIds);
    document.querySelector('#bh-add-high').addEventListener('click', () => addHighScoreJobsToQueue());
    document.querySelector('#bh-process-first').addEventListener('click', processFirstGreetingQueue);
    document.querySelector('#bh-view-queue').addEventListener('click', () => viewApplyQueue());
    document.querySelector('#bh-open-chat').addEventListener('click', () => window.open(CHAT_URL, '_blank'));
    refreshQueueStatus();

    document.querySelector('#bh-toggle').addEventListener('click', () => {
      const body = document.querySelector('#bh-body');
      const btn = document.querySelector('#bh-toggle');
      const hidden = body.style.display === 'none';
      body.style.display = hidden ? 'block' : 'none';
      btn.textContent = hidden ? '收起' : '展开';
    });
  }



  function createChatPanel() {
    if (document.querySelector('#boss-helper-panel')) return;

    const panel = document.createElement('div');
    panel.id = 'boss-helper-panel';
    panel.innerHTML = `
      <div class="bh-head">
        <b>BOSS投递队列</b>
        <button id="bh-toggle">收起</button>
      </div>
      <div id="bh-body">
        <div class="bh-row">
          <button id="bh-view-second">查看待发第二条</button>
          <button id="bh-send-second">发送当前会话第二条</button>
        </div>
        <div class="bh-row">
          <button id="bh-skip-second">跳过当前队列</button>
          <button id="bh-done-second">标记当前已完成</button>
        </div>
        <div id="bh-status">待操作</div>
        <div id="boss-helper-result">
          <div class="bh-empty">请先打开对应 HR 会话，再发送第二条介绍。</div>
        </div>
      </div>
    `;

    document.body.appendChild(panel);
    document.querySelector('#bh-view-second').addEventListener('click', () => viewApplyQueue('pending_second'));
    document.querySelector('#bh-send-second').addEventListener('click', sendSecondMessageForCurrentChat);
    document.querySelector('#bh-skip-second').addEventListener('click', skipCurrentSecondJob);
    document.querySelector('#bh-done-second').addEventListener('click', markCurrentSecondDone);
    document.querySelector('#bh-toggle').addEventListener('click', () => {
      const body = document.querySelector('#bh-body');
      const btn = document.querySelector('#bh-toggle');
      const hidden = body.style.display === 'none';
      body.style.display = hidden ? 'block' : 'none';
      btn.textContent = hidden ? '收起' : '展开';
    });
    refreshQueueStatus();
  }

  GM_addStyle(`
    #boss-helper-panel {
      position: fixed;
      right: 16px;
      bottom: 16px;
      z-index: 999999;
      width: 360px;
      max-height: 88vh;
      overflow: auto;
      background: #fff;
      border: 1px solid #ddd;
      border-radius: 10px;
      box-shadow: 0 8px 30px rgba(0,0,0,.18);
      font-size: 13px;
      color: #222;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, "Microsoft YaHei", sans-serif;
    }

    #boss-helper-panel .bh-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 10px 12px;
      border-bottom: 1px solid #eee;
      background: #f8f8f8;
      border-radius: 10px 10px 0 0;
    }

    #boss-helper-panel #bh-body {
      padding: 10px 12px 12px;
    }

    #boss-helper-panel label {
      display: block;
      margin-top: 8px;
      margin-bottom: 4px;
      color: #555;
      font-size: 12px;
    }

    #boss-helper-panel input,
    #boss-helper-panel textarea,
    #boss-helper-panel select {
      width: 100%;
      box-sizing: border-box;
      border: 1px solid #ddd;
      border-radius: 6px;
      padding: 6px 8px;
      font-size: 12px;
      outline: none;
      resize: vertical;
      background: #fff;
    }

    #boss-helper-panel button {
      border: 1px solid #ddd;
      background: #fff;
      border-radius: 6px;
      padding: 6px 8px;
      cursor: pointer;
      font-size: 12px;
    }

    #boss-helper-panel button:hover {
      background: #f4f4f4;
    }

    #boss-helper-panel .bh-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-top: 8px;
    }

    #bh-status {
      margin-top: 8px;
      color: #666;
      font-size: 12px;
    }

    #boss-helper-result {
      margin-top: 8px;
      padding: 8px;
      border-radius: 8px;
      background: #fafafa;
      border: 1px solid #eee;
      line-height: 1.7;
    }

    .bh-score {
      font-size: 24px;
      font-weight: 700;
      margin-bottom: 4px;
    }

    .bh-score.ok {
      color: #0a8f5a;
    }

    .bh-score.bad {
      color: #b54708;
    }

    .boss-helper-badge {
      position: absolute;
      right: 8px;
      top: 8px;
      z-index: 10;
      padding: 3px 6px;
      border-radius: 999px;
      font-size: 12px;
      background: #f5f5f5;
      border: 1px solid #ddd;
      pointer-events: none;
    }

    .boss-helper-badge.ok {
      color: #0a8f5a;
      border-color: #0a8f5a;
      background: #f0fff8;
    }

    .boss-helper-badge.bad {
      color: #b54708;
      border-color: #f0b27a;
      background: #fff7ed;
    }

    .boss-helper-card-ok {
      outline: 2px solid #0a8f5a !important;
      outline-offset: -2px;
    }
  `);

  const isJobsPage = location.href.includes('/web/geek/jobs') || location.href.includes('/web/geek/job');
  const isChatPage = location.href.includes('/web/geek/chat');

  if (isJobsPage) {
    createPanel();
    bindJobCardClickAutoAnalyze();

    setTimeout(() => {
      analyzeCurrentJob('init');
    }, 1500);
  }

  if (isChatPage) {
    createChatPanel();
  }

})();
