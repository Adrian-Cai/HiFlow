# HiFlow Local Service

第一阶段本地匹配服务，默认监听：

```text
http://127.0.0.1:8787
```

启动：

```bash
python local_service/server.py
```

接口：

- `GET /health`
- `GET /resumes`
- `POST /resumes`
- `POST /match`

`POST /resumes` 用于保存你的简历画像：

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

`POST /match` 请求：

```json
{
  "resume_id": "resume_001",
  "jd_text": "岗位 JD 文本",
  "source": "boss",
  "job_meta": {
    "title": "测试开发工程师",
    "company": "某公司",
    "salary": "20-35K",
    "location": "上海",
    "link": "https://www.zhipin.com/..."
  }
}
```

响应字段保持与扩展和旧 userscript 兼容：`score`、`decision`、`matched_points`、`missing_points`、`risk_points`、`suggested_first_message`、`suggested_second_message`。当前本地规则引擎以 `score >= 90` 作为推荐线。
