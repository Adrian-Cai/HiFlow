# HiFlow

HiFlow 是一个面向 BOSS 直聘岗位页的半自动岗位匹配助手。当前版本仍是油猴脚本，适合作为 MVP 验证：读取当前岗位 JD、计算匹配度、标记高分岗位，并辅助填入第一条打招呼话术。

## 推荐演进架构

油猴脚本适合做“页面点击、DOM 抓取、简单关键词打分”，但不适合承载正式版本里的简历上传、JD 理解、跨页面投递队列和复杂 AI 评分。更合理的正式形态是：

```text
Chrome / Edge 插件
负责：页面读取、右侧悬浮面板展示、上传简历、投递队列、按钮点击

本地后端服务
负责：简历解析、JD 解析、AI 匹配、评分、记录保存

大模型 / Embedding 模型
负责：判断简历和岗位是否匹配，返回分数、理由、风险点
```

当前脚本已经预留了对本地 `POST /match` 服务的调用能力，可以先用油猴验证页面 JD 抽取是否稳定，再逐步迁移到浏览器插件。

## 当前油猴脚本能力

- 读取 BOSS 岗位列表页右侧岗位详情 JD。
- 点击左侧岗位卡片后自动等待右侧详情同步，避免拿上一条岗位详情误判。
- 使用目标岗位词、核心关键词和排除词做本地关键词评分。
- 可选调用本地 AI 匹配服务，用 `resume_id + jd_text` 获取结构化评分结果。
- 扫描当前可见岗位卡片，给岗位卡片打分标记，并把高分岗位加入浏览器内存队列。
- 找到“立即沟通 / 继续沟通 / 打招呼”按钮后填入话术，但不会自动批量发送。

## 第一阶段扩展 MVP

仓库已新增正式方案的第一阶段骨架：

```text
extension/       Chrome/Edge Manifest V3 扩展
local_service/   localhost 本地匹配服务
docs/            阶段说明
```

启动本地服务：

```bash
python local_service/server.py
```

然后在 Chrome/Edge 扩展管理页加载 `extension/` 目录。扩展包含 jobs/chat content script、右侧悬浮面板和 service worker；service worker 会调用默认的 `http://127.0.0.1:8787/match`，并把当前匹配、扫描结果、投递队列和日志保存到 `chrome.storage.local`。

阶段详情见 [docs/phase-one-mvp.md](docs/phase-one-mvp.md)。

### 插件使用流程

1. 启动本地服务：`python local_service/server.py`。
2. 在 Edge 扩展管理页加载 `extension/` 目录。
3. 打开 BOSS jobs 页面。
4. 页面右侧会自动显示 HiFlow 悬浮面板；点击浏览器工具栏里的 HiFlow 图标可展开或收起。
5. 在“我的简历画像”里粘贴你的简历摘要、目标岗位、技能关键词和排除词，点击“保存简历画像”。
6. 确认“本地服务”为 `http://127.0.0.1:8787`，“阈值”默认为 `90`，“每批扫描数量”默认为 `8`。
7. 点击“分析当前岗位”可评分当前右侧岗位。
8. 点击“扫描当前批次”可给当前可见 8 个岗位批量评分。
9. 点击“扫描并准备打招呼”会扫描当前批次，只对分数 ≥ 90 的岗位点击沟通并填入话术。

如果勾选“自动点击发送”，HiFlow 会在填入话术后点击发送并继续下一个岗位；未勾选时会停在“已填入话术，待人工发送”。

## 本地 AI 匹配服务接口

在脚本面板勾选“使用本地AI匹配服务”后，脚本会把当前岗位详情发送到配置的 match 接口，默认地址：

```text
http://127.0.0.1:8787/match
```

请求示例：

```json
{
  "resume_id": "resume_001",
  "jd_text": "AI测试工程师 20-40K 上海 3-5年 本科 职位描述...",
  "source": "boss",
  "job_meta": {
    "title": "AI测试工程师",
    "company": "某公司",
    "salary": "20-40K",
    "location": "上海",
    "link": "https://www.zhipin.com/..."
  }
}
```

推荐返回：

```json
{
  "score": 88,
  "decision": "recommend",
  "title": "AI测试工程师",
  "hard_score": 90,
  "skill_score": 86,
  "experience_score": 92,
  "llm_score": 88,
  "matched_points": [
    "测试开发经验满足岗位要求",
    "自动化测试、接口测试、性能测试能力覆盖度高"
  ],
  "missing_points": [
    "AI测试项目细节可进一步补充"
  ],
  "risk_points": [
    "需要确认岗位是否偏业务测试"
  ]
}
```

如果本地服务不可用，脚本会自动回退到内置关键词评分，避免影响页面验证流程。

## 建议的后端接口

正式版本建议提供以下接口：

```text
POST /resume/upload   上传简历，返回 resume_id
GET  /resume/list     获取已上传简历列表
POST /resume/parse    重新解析简历
POST /match           传入 resume_id + jd_text，返回匹配结果
POST /queue/add       加入待投递队列
GET  /queue/list      查看投递队列
POST /queue/update    更新 pending_first / pending_second / done / skipped 等状态
```

## 开发路线

1. **V1 油猴验证版**：验证当前岗位 JD 抽取、按钮定位、本地 match 接口调用是否稳定。
2. **V2 Chrome 插件版**：增加简历上传、选择简历、右侧悬浮面板、投递队列、跨页面状态和聊天页跟进。
3. **V3 AI 匹配增强版**：增加简历画像、岗位画像、大模型评分、Pass 理由、风险提示和话术优化。
4. **V4 半自动投递闭环**：扫描当前页、自动加入高分队列、人工确认投递、失败重试和 CSV 导出。

## 安全边界

HiFlow 不绕过验证码、不自动批量发送消息，也不建议绕过平台限制。脚本只辅助读取页面、计算匹配度和填入话术，最终发送动作应由用户人工确认。
