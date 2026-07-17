# HiFlow Android 自动筛选

HiFlow 在 Android 真机上逐个读取 Boss 直聘岗位。默认运行完全只读的稳定性验证；真实沟通必须显式使用 `auto`，且必须先通过同设备、同 BOSS 版本、同代码与选择器版本的 50 岗位门禁。它不处理登录、短信、人脸或安全验证，也不会绕过平台限制。

## 首次安装

前置条件：Node.js 20.19+、npm 10+、Java、Android Platform Tools，以及已开启 USB 调试并完成授权的 Android 真机。

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\mobile_automation\setup.ps1
.\mobile_automation\run.ps1 doctor
```

只有 `deviceState` 为 `device`、`appiumPythonClient` 为 `installed` 且 `ok` 为 `true` 时再继续。

## 一键启动

在手机上登录 Boss 直聘，进入目标城市的岗位列表页，并设置“BOSS 三日内活跃”（列表显示“筛选·1”）。先运行 5 岗位只读冒烟：

```powershell
.\mobile_automation\start.ps1 verify --job-limit 5
```

确认冒烟通过后，从 0 正式验证 50 个岗位：

```powershell
.\mobile_automation\start.ps1 verify --job-limit 50
```

不带参数运行 `start.ps1` 也默认进入安全的 50 岗位 `verify` 模式。验证模式只启动 Appium，不启动匹配服务、不调用模型、不点击沟通按钮，也不写投递账本。报告保存在 `mobile_automation/data/verifications/`。

50 岗位报告为 `PASS` 后，才可单独启动真实沟通：

```powershell
.\mobile_automation\start.ps1 auto --resume-id resume_001
```

`auto` 使用纯本地确定性规则，匹配地址只允许 `127.0.0.1/localhost`，运行时不依赖 Codex 或其他 AI 判断。脚本只停止本次由它启动的服务，不会关闭原本已经运行的服务。

只验证服务能否启动，不读取岗位也不打招呼：

```powershell
.\mobile_automation\start.ps1 verify -CheckOnly
```

覆盖真实沟通参数：

```powershell
.\mobile_automation\start.ps1 auto --resume-id resume_001 `
  --minimum-salary-k 15 --threshold 90 `
  --batch-size 5 --cooldown-seconds 120 --daily-limit 150
```

## 中文日志

当前终端只显示容易理解的业务阶段：

```text
18:29:58 [验证] 12/50｜测试开发工程师｜示例科技｜已返回原列表
18:30:01 [岗位] 正在检查岗位：测试开发工程师｜示例科技｜20-30K｜今日活跃
18:30:02 [匹配] 测试开发工程师｜匹配度 95%
18:30:03 [沟通] 已成功打招呼：测试开发工程师｜今日累计 3/150
18:30:04 [跳过] 车载测试工程师｜原因：命中硬件、物联网、车载等禁投方向
18:30:05 [等待] 已完成一组沟通，暂停 120 秒后继续
```

完整 Appium 底层日志、Appium 控制台错误和匹配服务输出保存在：

```text
mobile_automation/data/logs/
```

Appium 控制台级别为 `error`，文件级别为 `debug`。日常观察当前终端即可；建立会话失败或控件定位异常时，再打开最新的 `appium-*.log`。

如果需要单独手动启动 Appium，也可以运行：

```powershell
.\mobile_automation\start-appium.ps1
```

## 默认筛选与节流

- `verify` 最多滚动 30 次，岗位之间不刷新；仅列表真正耗尽时刷新一次。任何超时、卡死、重连、沟通尝试或账本变化都会使正式验证失败。
- `auto` 启动前强制检查有效的 50 岗位 `PASS` 报告；设备、BOSS 版本、选择器或关键代码变化后必须重新验证。
- 当前岗位列表代表目标城市，进入详情页后不重复检查地址。
- 每次检查后直接返回原岗位列表位置，不重新点击岗位页签；优先处理当前可见的下一岗位，处理完后再向下续扫。
- 薪资按区间下限判断，下限必须不低于 15K；面议、日薪或无法可靠解析时跳过。
- 只处理招聘者今日活跃、近三日活跃或明确显示短时间内回复的岗位。
- 排除硬件、嵌入式、固件、物联网、车载测试、车联网、汽车电子、智能座舱和自动驾驶等方向。
- 匹配度至少 90，且匹配服务必须给出 `RECOMMEND` 且没有风险排除项。
- 每成功沟通 5 个岗位暂停 120 秒；按北京时间当日累计达到 150 个后停止。
- 检测到安全验证、登录失效、账号异常或平台沟通上限时立即停止，等待人工处理。

成功记录保存在 `mobile_automation/data/applications.jsonl`，用于跨次运行去重和计算当日累计量。不会保存验证码、手机号、Cookie、登录凭据或聊天内容。

## 测试

```powershell
python -m unittest discover -s tests -v
```
