$ErrorActionPreference = 'Stop'

$RuntimeRoot = if ($env:APPIUM_RUNTIME_HOME) { $env:APPIUM_RUNTIME_HOME } else { 'D:\Appium' }
$Python = if ($env:APPIUM_PYTHON) { $env:APPIUM_PYTHON } else { Join-Path $RuntimeRoot '.venv\Scripts\python.exe' }

if (-not (Test-Path $Python)) {
    throw "Shared Appium Python client is missing at $Python. Run .\mobile_automation\setup.ps1 first."
}

& $Python -m mobile_automation @args
exit $LASTEXITCODE
