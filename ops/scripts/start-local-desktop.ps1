[CmdletBinding()]
param(
  [string]$HomeDir = "$env:LOCALAPPDATA\ZhiyiNative\default",
  [switch]$CheckOnly,
  [switch]$NoPause,
  [switch]$WatchBackend,
  # "open" only adds the terminal service and never restarts healthy services, so a
  # crashed frontend dev server or a closed desktop window leaves the stack partially
  # running and refuses to start. Use -Recover to stop the recorded stack and start it
  # again with the same identity (data, workspace and credentials are preserved).
  [switch]$Recover
)

# 启动前会先接管运行时端口：占用 15432/16379/18761/18765/18080/15200/18766/19222
# 的残留进程（上一次的 dev server、孤儿服务等）会被停掉，然后绑定知弈自己的服务。
# 启动器自身、其父进程、不可检查的进程与 Windows 会话关键进程会被拒绝而不是强杀。

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = Join-Path $env:LOCALAPPDATA 'ZhiyiNative\python\Scripts\python.exe'
$runtime = Join-Path $PSScriptRoot 'infra\windows\native\persistent_runtime.py'

try {
  foreach ($required in @($python, $runtime, (Join-Path $HomeDir 'environment.json'))) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
      throw "Required local runtime file not found: $required"
    }
  }
  if ($CheckOnly) {
    Write-Host 'Local desktop launcher checks passed.'
    exit 0
  }
  Set-Location $repoRoot
  Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
  Write-Host 'Starting local services and Electron. Please wait...' -ForegroundColor Cyan
  Write-Host "Home: $HomeDir"
  $startupTimer = [System.Diagnostics.Stopwatch]::StartNew()
  if ($Recover -and $WatchBackend) { throw 'Use either -Recover or -WatchBackend, not both.' }
  if ($WatchBackend) {
    Write-Host 'Enabling TypeScript backend source watching (only the backend is switched)...' -ForegroundColor Cyan
    & $python -u $runtime watch-backend --home $HomeDir
  } elseif ($Recover) {
    Write-Host 'Recovering: stopping the recorded stack first (all data is preserved)...' -ForegroundColor Yellow
    & $python -u $runtime recover --home $HomeDir --desktop
  } else {
    & $python -u $runtime open --home $HomeDir
  }
  $runtimeExitCode = $LASTEXITCODE
  if ($runtimeExitCode -ne 0) {
    if (-not $Recover) {
      Write-Host 'If the error reports that local services are only partially running, inspect status/logs, then explicitly recover with:' -ForegroundColor Yellow
      Write-Host "  & '$PSCommandPath' -Recover" -ForegroundColor Yellow
    }
    throw "Local startup failed after $([math]::Round($startupTimer.Elapsed.TotalSeconds, 1))s (exit $runtimeExitCode). See $HomeDir\logs."
  }
  Write-Host "Local desktop ready in $([math]::Round($startupTimer.Elapsed.TotalSeconds, 1))s." -ForegroundColor Green
} catch {
  Write-Host $_.Exception.Message -ForegroundColor Red
  if ($_.Exception.Message -like '*partially running*') {
    Write-Host 'Only part of the local stack is running. "open" never restarts healthy services.' -ForegroundColor Yellow
    Write-Host 'To restart the whole recorded stack (data is preserved) run:' -ForegroundColor Yellow
    Write-Host "  & '$PSCommandPath' -Recover" -ForegroundColor Yellow
  }
  if (-not $CheckOnly -and -not $NoPause) { [void](Read-Host 'Startup has failed. Press Enter to close this window') }
  exit 1
}
