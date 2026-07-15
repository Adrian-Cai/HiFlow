$ErrorActionPreference = 'Stop'

$ModuleRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RuntimeRoot = if ($env:APPIUM_RUNTIME_HOME) { $env:APPIUM_RUNTIME_HOME } else { 'D:\Appium' }
$env:APPIUM_HOME = Join-Path $RuntimeRoot '.appium-home'
$Adb = Get-Command adb -ErrorAction Stop
$env:ANDROID_HOME = Split-Path -Parent (Split-Path -Parent $Adb.Source)
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$Appium = Join-Path $RuntimeRoot 'node_modules\.bin\appium.cmd'

if (-not (Test-Path $Appium)) {
    throw "未找到 Appium：$Appium。请先运行 .\mobile_automation\setup.ps1。"
}

$LogDir = Join-Path $ModuleRoot 'data\logs'
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$Timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$AppiumLog = Join-Path $LogDir "appium-$Timestamp.log"

Write-Host "$(Get-Date -Format 'HH:mm:ss') [启动] 正在启动 Appium 手机自动化服务，地址：http://127.0.0.1:4723"
Write-Host "$(Get-Date -Format 'HH:mm:ss') [日志] 终端只显示错误；完整 Appium 底层日志：$AppiumLog"
Write-Host "$(Get-Date -Format 'HH:mm:ss') [提示] 此服务需要保持运行，按 Ctrl+C 可以停止。"

& $Appium `
    --address 127.0.0.1 `
    --port 4723 `
    --log $AppiumLog `
    --log-level 'error:debug' `
    --log-no-colors `
    --log-timestamp `
    --local-timezone
