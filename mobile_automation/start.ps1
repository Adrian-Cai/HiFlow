param(
    [string]$ResumeId = 'resume_001',
    [switch]$CheckOnly,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$AutoArguments
)

$ErrorActionPreference = 'Stop'

$ModuleRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ModuleRoot
$RuntimeRoot = if ($env:APPIUM_RUNTIME_HOME) { $env:APPIUM_RUNTIME_HOME } else { 'D:\Appium' }
$Python = if ($env:APPIUM_PYTHON) { $env:APPIUM_PYTHON } else { Join-Path $RuntimeRoot '.venv\Scripts\python.exe' }
$Appium = Join-Path $RuntimeRoot 'node_modules\.bin\appium.cmd'
$RunScript = Join-Path $ModuleRoot 'run.ps1'
$LogDir = Join-Path $ModuleRoot 'data\logs'
$Timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$AppiumFullLog = Join-Path $LogDir "appium-$Timestamp.log"
$MatcherProcess = $null
$AppiumProcess = $null
$ExitCode = 2

function Write-Stage([string]$Category, [string]$Message) {
    Write-Host "$(Get-Date -Format 'HH:mm:ss') [$Category] $Message"
}

function Test-Service([string]$Uri) {
    try {
        Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 2 | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

function Wait-Service(
    [string]$Name,
    [string]$Uri,
    [System.Diagnostics.Process]$Process,
    [string]$FailureLog
) {
    $Deadline = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $Deadline) {
        if (Test-Service $Uri) {
            Write-Stage '就绪' "$Name 已启动。"
            return
        }
        if ($null -ne $Process -and $Process.HasExited) {
            throw "$Name 启动后意外退出，请查看日志：$FailureLog"
        }
        Start-Sleep -Milliseconds 500
    }
    throw "$Name 在 45 秒内没有就绪，请查看日志：$FailureLog"
}

function Stop-ChildService([System.Diagnostics.Process]$Process, [string]$Name) {
    if ($null -ne $Process -and -not $Process.HasExited) {
        Write-Stage '清理' "正在停止本次自动启动的$Name。"
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
    }
}

try {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    Write-Stage '启动' "HiFlow 一键任务开始，使用简历：$ResumeId"
    Write-Stage '日志' "业务进度显示在当前终端；底层排障日志目录：$LogDir"

    if (-not (Test-Path -LiteralPath $Python)) {
        throw "未找到 Python 客户端：$Python。请先运行 .\mobile_automation\setup.ps1。"
    }
    if (-not (Test-Path -LiteralPath $Appium)) {
        throw "未找到 Appium：$Appium。请先运行 .\mobile_automation\setup.ps1。"
    }

    if (Test-Service 'http://127.0.0.1:8787/health') {
        Write-Stage '复用' '本地岗位匹配服务已经运行。'
    }
    else {
        Write-Stage '启动' '正在启动本地岗位匹配服务……'
        $env:PYTHONUNBUFFERED = '1'
        $MatcherProcess = Start-Process `
            -FilePath $Python `
            -ArgumentList @('-u', (Join-Path $RepoRoot 'local_service\server.py')) `
            -WorkingDirectory $RepoRoot `
            -PassThru `
            -WindowStyle Hidden
        Wait-Service '本地岗位匹配服务' 'http://127.0.0.1:8787/health' $MatcherProcess $LogDir
    }

    if (Test-Service 'http://127.0.0.1:4723/status') {
        Write-Stage '复用' 'Appium 手机自动化服务已经运行。'
    }
    else {
        Write-Stage '启动' '正在启动 Appium 手机自动化服务……'
        $Adb = Get-Command adb -ErrorAction Stop
        $env:APPIUM_HOME = Join-Path $RuntimeRoot '.appium-home'
        $env:ANDROID_HOME = Split-Path -Parent (Split-Path -Parent $Adb.Source)
        $env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
        $AppiumArguments = @(
            '--address', '127.0.0.1',
            '--port', '4723',
            '--log', $AppiumFullLog,
            '--log-level', 'error:debug',
            '--log-no-colors',
            '--log-timestamp',
            '--local-timezone'
        )
        $AppiumProcess = Start-Process `
            -FilePath $Appium `
            -ArgumentList $AppiumArguments `
            -WorkingDirectory $RepoRoot `
            -PassThru `
            -WindowStyle Hidden
        Write-Stage '日志' "完整 Appium 底层日志：$AppiumFullLog"
        Wait-Service 'Appium 手机自动化服务' 'http://127.0.0.1:4723/status' $AppiumProcess $AppiumFullLog
    }

    Write-Stage '检查' '依赖服务已就绪；请保持手机解锁，并停留在目标城市的岗位列表页。'
    if ($CheckOnly) {
        Write-Stage '完成' '启动检查通过；未读取岗位，也未执行打招呼。'
        $ExitCode = 0
        return
    }
    Write-Stage '执行' '开始逐个识别岗位并按规则决定是否打招呼。'
    & $RunScript auto --resume-id $ResumeId @AutoArguments
    $ExitCode = $LASTEXITCODE
}
catch {
    Write-Stage '失败' $_.Exception.Message
    Write-Stage '日志' "如需排查，请查看：$LogDir"
    $ExitCode = 2
}
finally {
    Stop-ChildService $AppiumProcess ' Appium 服务'
    Stop-ChildService $MatcherProcess '匹配服务'
}

exit $ExitCode
