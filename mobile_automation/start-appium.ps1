$ErrorActionPreference = 'Stop'

$RuntimeRoot = if ($env:APPIUM_RUNTIME_HOME) { $env:APPIUM_RUNTIME_HOME } else { 'D:\Appium' }
$env:APPIUM_HOME = Join-Path $RuntimeRoot '.appium-home'
$Adb = Get-Command adb -ErrorAction Stop
$env:ANDROID_HOME = Split-Path -Parent (Split-Path -Parent $Adb.Source)
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$Appium = Join-Path $RuntimeRoot 'node_modules\.bin\appium.cmd'

if (-not (Test-Path $Appium)) {
    throw "Shared Appium is missing at $Appium. Run .\mobile_automation\setup.ps1 first."
}

& $Appium --address 127.0.0.1 --port 4723
