# HiFlow Phase 1 MVP

第一阶段目标：把 HiFlow 从单文件 userscript 迁移到“浏览器扩展 + localhost 本地匹配服务”的正式骨架。

## 交付范围

- MV3 unpacked extension，目录为 `extension/`。
- jobs 页 content script：
  - 采集右侧岗位详情。
  - 扫描当前可见岗位卡片。
  - 点击卡片后等待右侧详情与左侧卡片同步。
- chat 页 content script：
  - 采集当前会话基础状态。
- service worker：
  - 作为 content script、悬浮面板、本地服务之间的消息总线。
  - 调用 `localhost /match`。
  - 使用 `chrome.storage.local` 保存当前结果、扫描结果、队列和日志。
- 右侧悬浮面板：
  - 配置本地服务地址、简历 ID、阈值。
  - 保存简历画像：摘要、目标岗位、技能关键词、排除词。
  - 分析当前岗位。
  - 扫描当前批次，默认每批 8 个岗位。
  - 扫描并准备打招呼：对分数达到 90 的岗位打开沟通并填入话术。
  - 将当前岗位或推荐岗位加入队列。
  - 查看 chat 状态与运行日志。
- localhost 服务：
  - `GET /health`
  - `GET /resumes`
  - `POST /resumes`
  - `POST /match`

## 启动本地服务

```bash
python local_service/server.py
```

健康检查：

```bash
curl http://127.0.0.1:8787/health
```

## 加载扩展

1. 打开 Chrome 或 Edge 扩展管理页。
2. 开启开发者模式。
3. 选择“加载已解压的扩展”。
4. 选择仓库中的 `extension/` 目录。
5. 打开 BOSS jobs 或 chat 页面，HiFlow 会自动悬浮在页面右侧；点击工具栏图标可展开或收起。

## 本阶段不做

- 默认不自动批量发送消息；只有勾选“自动点击发送”后才会点击发送按钮。
- 不绕过验证码或平台限制。
- 不上传原始简历文件。
- 不接入真实 LLM API。
- 不做 Native Messaging 安装器。

## 第二阶段建议

- 将队列状态扩展为 `PENDING_APPLY / PENDING_SECOND / DONE / SKIPPED` 的完整状态机。
- 在 jobs 页实现人工确认后的逐个投递。
- 在 chat 页实现待发第二条队列的人工确认发送。
- 将本地服务升级为 FastAPI + SQLite，并接入真实简历解析。
