# HiFlow 本地匹配服务

本服务为 Android 自动化流程提供简历画像和岗位匹配能力，默认监听 `http://127.0.0.1:8787`。

## 启动

```powershell
python local_service\server.py
```

## 接口

- `GET /health`
- `GET /resumes`
- `POST /resumes`
- `POST /match`

保存简历画像：

```json
{
  "id": "resume_001",
  "name": "AI测试/测试开发",
  "summary": "6年测试开发经验，覆盖自动化、接口测试、性能压测、CI/CD、质量平台和AI测试提效。",
  "target_titles": ["测试开发", "自动化测试", "AI测试"],
  "skills": ["Python", "Postman", "JMeter", "Playwright", "CI/CD"],
  "exclude_keywords": ["销售", "客服", "外包驻场"]
}
```

岗位匹配请求：

```json
{
  "resume_id": "resume_001",
  "jd_text": "岗位 JD 文本",
  "source": "boss-app",
  "job_meta": {
    "title": "测试开发工程师",
    "company": "某公司",
    "salary": "20-35K",
    "location": "上海"
  }
}
```

响应包含 `score`、`decision`、`matched_points`、`missing_points`、`risk_points`、`suggested_first_message` 和 `suggested_second_message`。本地服务以 `score >= 80` 标记可推荐结果；Android `auto` 主流程使用更严格的 `score >= 90` 自动沟通线，并在评分前执行薪资、活跃度和领域硬过滤。
