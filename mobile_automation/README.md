# HiFlow Android 自动筛选

HiFlow 在 Android 真机上逐个读取 Boss 直聘岗位，在当前详情页完成硬过滤、简历匹配和打招呼。它不处理登录、短信、人脸或安全验证，也不会绕过平台限制。

## 首次安装

前置条件：Node.js 20.19+、npm 10+、Java、Android Platform Tools，以及已开启 USB 调试并完成授权的 Android 真机。

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\mobile_automation\setup.ps1
.\mobile_automation\run.ps1 doctor
```

只有 `deviceState` 为 `device`、`appiumPythonClient` 为 `installed` 且 `ok` 为 `true` 时再继续。

## 一键启动

在手机上登录 Boss 直聘，并停留在目标城市的岗位列表页，然后运行：

```powershell
.\mobile_automation\start.ps1
```

脚本会自动检查并按需启动本地岗位匹配服务和 Appium，默认使用 `resume_001`，随后开始逐岗位处理。脚本只停止本次由它启动的服务，不会关闭原本已经运行的服务。

只验证服务能否启动，不读取岗位也不打招呼：

```powershell
.\mobile_automation\start.ps1 -CheckOnly
```

使用其他简历或覆盖默认参数：

```powershell
.\mobile_automation\start.ps1 -ResumeId resume_001 `
  --minimum-salary-k 15 --threshold 90 `
  --batch-size 5 --cooldown-seconds 120 --daily-limit 150
```

## 中文日志

当前终端只显示容易理解的业务阶段：

```text
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
