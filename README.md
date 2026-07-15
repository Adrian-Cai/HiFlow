# HiFlow

HiFlow 是一个面向 Boss 直聘 Android App 的岗位筛选与打招呼工具。项目通过 Appium 操作 Android 真机：逐个打开岗位详情，在当前详情页完成硬过滤、简历匹配和即时沟通。

项目不处理登录、短信、人脸或安全验证，不绕过平台限制；遇到风控、登录失效或沟通上限时会暂停并保存进度。

## 项目结构

```text
mobile_automation/  Android 真机自动化、逐岗位工作流与 Appium 适配
local_service/      简历画像与岗位匹配服务
tests/              APP 自动化单元测试
```

当前仓库只保留 Android 自动化主线及其必需的本地匹配能力。

## 快速开始

前置条件：Node.js 20.19+、npm 10+、Java、Android Platform Tools，以及已开启 USB 调试的 Android 真机。

首次安装共享 Appium 与 Python 运行环境：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\mobile_automation\setup.ps1
```

检查设备和运行环境：

```powershell
.\mobile_automation\run.ps1 doctor
```

手机端手动登录 Boss 直聘并进入目标城市的岗位列表后，一条命令启动匹配服务、Appium 和自动筛选：

```powershell
.\mobile_automation\start.ps1
```

终端只显示中文业务进度；Appium 等底层排障日志保存在 `mobile_automation/data/logs/`。只检查服务、不读取岗位也不打招呼时，运行 `.\mobile_automation\start.ps1 -CheckOnly`。

默认要求岗位月薪下限不低于 15K、招聘者 3 日内活跃、匹配分不低于 90，并排除硬件、嵌入式、物联网和车载方向。每成功沟通 5 个岗位冷却 120 秒，按北京时间当日累计达到 150 个后停止。

安装细节、暂停恢复、选择器维护和安全边界见 [mobile_automation/README.md](mobile_automation/README.md)，匹配接口见 [local_service/README.md](local_service/README.md)。

## 测试

```powershell
python -m unittest discover -s tests -v
```
