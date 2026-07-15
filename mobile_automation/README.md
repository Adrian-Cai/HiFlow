# HiFlow Android Appium

Android 真机上的逐岗位筛选与即时沟通工具。它不会处理登录、短信、人脸或安全验证，也不会绕过平台限制。

## 工作流

1. `auto` 从用户已经选择的目标城市岗位列表开始逐个读取卡片。
2. 仅打开“今日/近三日活跃”或“分钟/小时内回复”的岗位详情，展开“查看更多”并读取完整职位描述。
3. 在评分前检查薪资下限（默认 15K）和领域禁投项，排除硬件、嵌入式、物联网、车载等岗位。
4. 将完整职位描述发送给本地 `/match` 服务；自动沟通线为 90 分，同时要求 `decision=RECOMMEND` 且无排除项。
5. 条件通过后直接点击当前详情页的沟通按钮，不返回列表重新查找岗位。
6. 只有新沟通成功才写入台账；每成功 5 个冷却 120 秒，按北京时间当日达到 150 个后停止。
7. 检测到安全验证、登录失效、账号异常或平台沟通上限时立即停止，等待人工处理。

## 首次安装

前置条件：Node.js 20.19+、npm 10+、Java、Android Platform Tools，以及已开启 USB 调试的 Android 真机。

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\mobile_automation\setup.ps1
```

Appium 服务端、UiAutomator2 driver 和 Python 客户端统一安装在共享目录 `D:\Appium`，项目内不保存 `.venv`、`node_modules` 或 Appium Home。其他项目可以复用同一套 Appium 服务端和 `$env:APPIUM_PYTHON` 解释器。
脚本会从当前 `adb.exe` 位置推导 `ANDROID_HOME`；当前环境会解析为 `D:\`，因为 ADB 位于 `D:\platform-tools\`。
UiAutomator2 自带 doctor 还会检查模拟器和完整 Android SDK；本方案使用真机，因此缺少 `emulator` 会显示警告。最终准入以 HiFlow 的 `python -m mobile_automation doctor` 为准。

在手机弹出 USB 调试授权时解锁手机并选择允许，然后检查：

```powershell
.\mobile_automation\run.ps1 doctor
```

只有 `deviceState` 为 `device`、`appiumPythonClient` 为 `installed` 且 `ok` 为 `true` 时才继续。

## 启动

终端一，启动现有本地匹配服务：

```powershell
python local_service\server.py
```

终端二，启动 `D:\Appium` 中的共享 Appium 3：

```powershell
.\mobile_automation\start-appium.ps1
```

手机端手动登录 Boss 直聘并进入目标城市的岗位列表，然后运行：

```powershell
.\mobile_automation\run.ps1 auto --resume-id resume_001
```

默认值也可以显式指定：

```powershell
.\mobile_automation\run.ps1 auto --resume-id resume_001 `
  --minimum-salary-k 15 --threshold 90 `
  --batch-size 5 --cooldown-seconds 120 --daily-limit 150
```

当前岗位列表代表目标城市，详情页地址只记录、不参与过滤。薪资按区间下限判断；`15-20K` 和 `15K以上` 在 15K 门槛下通过，`14-25K`、面议、日薪或无法解析的格式跳过。

旧的 `scan/apply/resume/status` 批次命令仅为已有数据保留兼容，新流程不依赖批次回查。

## 选择器与安全边界

- 版本化选择器在 `selectors.v1.json`；优先使用资源 ID/可访问性描述，默认 XPath 只是首次真机 PoC 的保守降级。
- 如果岗位或沟通按钮定位不唯一，运行会失败并停止，不使用坐标盲点。
- `继续沟通` 视为已经沟通过，不会再次点击，也不会增加当日成功数。
- 成功台账位于 `mobile_automation/data/applications.jsonl`；它用于跨重启去重和按北京时间累计当日成功数。
- 台账只保存岗位摘要、匹配结果、指纹和时间；不保存页面源码、聊天内容、验证码、手机号、Cookie 或登录凭据。
- Boss App 升级后应先运行单岗位扫描并更新选择器，再恢复批次执行。

## 测试

```powershell
python -m unittest discover -s tests -v
```
