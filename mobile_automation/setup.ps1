$ErrorActionPreference = 'Stop'

$ModuleRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ModuleRoot
$RuntimeRoot = if ($env:APPIUM_RUNTIME_HOME) { $env:APPIUM_RUNTIME_HOME } else { 'D:\Appium' }
$env:APPIUM_RUNTIME_HOME = $RuntimeRoot
$env:APPIUM_HOME = Join-Path $RuntimeRoot '.appium-home'
$Adb = Get-Command adb -ErrorAction Stop
$env:ANDROID_HOME = Split-Path -Parent (Split-Path -Parent $Adb.Source)
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$Appium = Join-Path $RuntimeRoot 'node_modules\.bin\appium.cmd'
$Venv = Join-Path $RuntimeRoot '.venv'
$VenvPython = Join-Path $Venv 'Scripts\python.exe'

function Assert-LastExitCode([string]$Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE"
    }
}

New-Item -ItemType Directory -Path $RuntimeRoot -Force | Out-Null
if (-not (Test-Path $Appium)) {
    npm install --prefix $RuntimeRoot appium@3.5.2 --save-exact
    Assert-LastExitCode 'Shared Appium installation'
}

$InstalledDrivers = & $Appium driver list --installed
Assert-LastExitCode 'Appium driver list'
if ($InstalledDrivers -notmatch 'uiautomator2') {
    & $Appium driver install uiautomator2
    Assert-LastExitCode 'Appium UiAutomator2 driver install'
}
& $Appium driver doctor uiautomator2
if ($LASTEXITCODE -ne 0) {
    Write-Warning 'Appium doctor reported an incomplete full Android SDK. HiFlow uses a real device; run the Python doctor below and do not continue until deviceState is device.'
}

if (-not (Test-Path $VenvPython)) {
    python -m venv $Venv
    Assert-LastExitCode 'Python virtual environment creation'
}

& $VenvPython -c 'import appium'
if ($LASTEXITCODE -ne 0) {
    & $VenvPython -m pip install --disable-pip-version-check -r (Join-Path $ModuleRoot 'requirements.txt')
    Assert-LastExitCode 'Python dependency installation'
}

[Environment]::SetEnvironmentVariable('APPIUM_RUNTIME_HOME', $RuntimeRoot, 'User')
[Environment]::SetEnvironmentVariable('APPIUM_HOME', $env:APPIUM_HOME, 'User')
[Environment]::SetEnvironmentVariable('APPIUM_PYTHON', $VenvPython, 'User')
[Environment]::SetEnvironmentVariable('ANDROID_HOME', $env:ANDROID_HOME, 'User')
[Environment]::SetEnvironmentVariable('ANDROID_SDK_ROOT', $env:ANDROID_SDK_ROOT, 'User')

$AppiumBin = Split-Path -Parent $Appium
$UserPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (($UserPath -split ';') -notcontains $AppiumBin) {
    [Environment]::SetEnvironmentVariable('Path', (($UserPath.TrimEnd(';') + ';' + $AppiumBin).TrimStart(';')), 'User')
}

Write-Host "Shared Appium runtime is ready in $RuntimeRoot"
Write-Host "HiFlow repository: $RepoRoot"
Write-Host 'Next: .\mobile_automation\run.ps1 doctor'
