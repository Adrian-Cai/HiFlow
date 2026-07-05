(function () {
  'use strict';

  const SECTION_TITLES = [
    '个人优势',
    '工作经历',
    '项目经历',
    '教育经历',
    '求职期望',
    '专业技能',
    '技能',
    '资格证书',
    '证书'
  ];

  const SKILL_KEYWORDS = [
    'JavaScript', 'TypeScript', 'Python', 'Java', 'Go', 'Node.js', 'React', 'Vue',
    'Next.js', 'Django', 'Flask', 'Spring Boot', 'MySQL', 'PostgreSQL', 'Redis',
    'MongoDB', 'Docker', 'Kubernetes', 'Linux', 'Git', 'Jenkins', 'CI/CD',
    'Selenium', 'Playwright', 'Cypress', 'JMeter', 'Postman', 'pytest', 'Allure',
    '自动化测试', '性能测试', '接口测试', '测试开发', '质量保障', '数据分析',
    '大模型', 'AI', 'Prompt', '产品设计', '项目管理'
  ];

  function getCleanText(root = document.body) {
    const clone = root.cloneNode(true);
    clone.querySelectorAll('script, style, noscript, svg, canvas').forEach(node => node.remove());
    return (clone.innerText || clone.textContent || '')
      .replace(/\r/g, '\n')
      .replace(/[ \t]+/g, ' ')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  }

  function getVisibleText(el) {
    if (!el) return '';
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    if (!rect.width || !rect.height || style.display === 'none' || style.visibility === 'hidden') return '';
    return (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
  }

  function getLines(text) {
    return String(text || '')
      .split('\n')
      .map(line => line.trim())
      .filter(Boolean);
  }

  function pickName(lines) {
    const selectors = [
      '[class*="name"]',
      '[class*="user"]',
      '[class*="base"] h1',
      'h1',
      'h2'
    ];

    for (const selector of selectors) {
      const value = getVisibleText(document.querySelector(selector));
      if (isLikelyName(value)) return value;
    }

    return lines.find(isLikelyName) || 'BOSS 在线简历';
  }

  function isLikelyName(value) {
    const text = String(value || '').trim();
    return Boolean(
      text &&
      text.length >= 2 &&
      text.length <= 20 &&
      !/[：:|/\\]/.test(text) &&
      !/(BOSS|直聘|简历|编辑|预览|求职|沟通|登录|附件)/i.test(text)
    );
  }

  function extractSections(lines) {
    const sections = {};
    let currentTitle = '简历正文';

    for (const line of lines) {
      const matchedTitle = SECTION_TITLES.find(title => line === title || line.startsWith(`${title} `));
      if (matchedTitle) {
        currentTitle = matchedTitle;
        sections[currentTitle] = sections[currentTitle] || [];
        continue;
      }

      sections[currentTitle] = sections[currentTitle] || [];
      sections[currentTitle].push(line);
    }

    return sections;
  }

  function inferTargetTitles(lines, sections) {
    const source = [
      ...(sections['求职期望'] || []),
      ...lines.filter(line => /工程师|测试|开发|产品|运营|设计|经理|架构|算法|数据/.test(line))
    ];

    const titles = [];
    for (const line of source) {
      const parts = line
        .split(/[，,、/|]/)
        .map(part => part.trim())
        .filter(Boolean);

      for (const part of parts) {
        if (
          part.length >= 2 &&
          part.length <= 28 &&
          /工程师|测试|开发|产品|运营|设计|经理|架构|算法|数据/.test(part) &&
          !/薪|面议|城市|行业|经验/.test(part)
        ) {
          titles.push(part);
        }
      }
    }

    return unique(titles).slice(0, 12);
  }

  function inferSkills(text, sections) {
    const skillText = [
      ...(sections['专业技能'] || []),
      ...(sections['技能'] || []),
      text
    ].join('\n');

    const matched = SKILL_KEYWORDS.filter(skill => {
      const pattern = new RegExp(escapeRegExp(skill), 'i');
      return pattern.test(skillText);
    });

    return unique(matched).slice(0, 40);
  }

  function buildSummary(name, sections, rawText) {
    const preferredTitles = ['个人优势', '工作经历', '项目经历', '教育经历', '专业技能', '资格证书'];
    const parts = [`姓名：${name}`];

    for (const title of preferredTitles) {
      const content = (sections[title] || []).join('\n').trim();
      if (content) parts.push(`${title}：\n${content}`);
    }

    const summary = parts.join('\n\n').trim();
    return (summary || rawText).slice(0, 16000);
  }

  function unique(items) {
    const seen = new Set();
    return items.filter(item => {
      const key = String(item || '').trim().toLowerCase();
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  function escapeRegExp(value) {
    return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  function collectResumeProfile() {
    const rawText = getCleanText();
    const lines = getLines(rawText);
    const sections = extractSections(lines);
    const name = pickName(lines);
    const targetTitles = inferTargetTitles(lines, sections);
    const skills = inferSkills(rawText, sections);

    return {
      ok: rawText.length >= 80,
      page: 'resume',
      resume: {
        name,
        summary: buildSummary(name, sections, rawText),
        targetTitles,
        skills,
        excludeKeywords: '',
        source: 'boss-resume-page',
        rawText: rawText.slice(0, 16000),
        collectedAt: new Date().toISOString()
      }
    };
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message?.type !== 'HIFLOW_COLLECT_RESUME_PROFILE') return false;

    try {
      sendResponse(collectResumeProfile());
    } catch (error) {
      sendResponse({ ok: false, error: error.message });
    }

    return false;
  });

  chrome.runtime.sendMessage({
    type: 'HIFLOW_PAGE_READY',
    payload: {
      page: 'resume',
      url: location.href,
      title: document.title
    }
  }).catch(() => {});
})();
