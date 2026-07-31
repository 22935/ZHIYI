#!/usr/bin/env pwsh
param(
    [ValidateSet("lawyer", "teacher", "programmer", "writer")]
    [string]$Role = "lawyer",
    [int]$Port = 8000,
    [switch]$Docker,
    [switch]$NoBuild
)

$ErrorActionPreference = "Stop"
$PYTHON = "C:/Users/LZX/AppData/Local/Programs/Python/Python314/python.exe"
$TUI_SRC = Join-Path $PSScriptRoot "src"
$REPO_ROOT = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$COMPOSE_FILES = @(
    (Join-Path $REPO_ROOT "compose.yaml"),
    (Join-Path $REPO_ROOT "compose.dev.yaml"),
    (Join-Path $REPO_ROOT "compose.windows.yaml")
)
$COMPOSE_ENV_FILE = Join-Path $REPO_ROOT ".env.windows"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$TUI_SRC;$env:PYTHONPATH"
} else {
    $env:PYTHONPATH = $TUI_SRC
}

function Test-HttpHealth {
    param([int]$HealthPort)

    $client = [System.Net.Http.HttpClient]::new()
    try {
        $client.Timeout = [TimeSpan]::FromSeconds(2)
        $url = "http://127.0.0.1:$HealthPort/health"
        $response = $client.GetAsync(
            $url,
            [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead
        ).GetAwaiter().GetResult()
        try {
            return $response.IsSuccessStatusCode
        } finally {
            $response.Dispose()
        }
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " ZhiYi AgentOS TUI Launcher" -ForegroundColor Cyan
Write-Host " Role: $Role  |  API: http://127.0.0.1:$($Port)/ai" -ForegroundColor Cyan
if ($NoBuild) {
    Write-Host " Mode: Docker shared backend (reuse existing image)" -ForegroundColor Magenta
} else {
    Write-Host " Mode: Docker shared backend (rebuild ai-service)" -ForegroundColor Magenta
}
Write-Host "============================================" -ForegroundColor Cyan

Write-Host ""
$buildLabel = if ($NoBuild) { "Starting" } else { "Building/restarting" }
Write-Host "[1/2] $buildLabel Docker ai-service..." -ForegroundColor Yellow
if (-not (Test-Path -LiteralPath $COMPOSE_ENV_FILE -PathType Leaf)) {
    throw "Windows Compose environment file does not exist: $COMPOSE_ENV_FILE"
}
$composeArgs = @()
foreach ($composeFile in $COMPOSE_FILES) {
    $composeArgs += @("-f", $composeFile)
}
$composeArgs += @("--env-file", $COMPOSE_ENV_FILE, "--profile", "debug-ports")
$env:KINLIN_AI_DEBUG_PORT = "$Port"
$upArgs = @("up", "-d")
if (-not $NoBuild) {
    $upArgs += "--build"
}
$upArgs += @("ai-service", "ai-debug-port")
docker compose @composeArgs @upArgs 2>&1

Write-Host "       Waiting for ai-service..." -NoNewline
$ok = $false
for ($i = 0; $i -lt 90; $i++) {
    Start-Sleep -Milliseconds 2000
    if (Test-HttpHealth $Port) {
        Write-Host " OK" -ForegroundColor Green
        $ok = $true
        break
    } else {
        Write-Host "." -NoNewline
    }
}
if (-not $ok) {
    Write-Host " TIMEOUT" -ForegroundColor Red
    Write-Host "       Check the canonical Compose stack with .\scripts\infra\windows\status.ps1" -ForegroundColor Red
    exit 1
}

Write-Host "[2/2] Starting TUI..." -ForegroundColor Yellow
$env:AGENTOS_API_URL = "http://127.0.0.1:$Port/ai"
& $PYTHON -m kinlin_tui.app os --role $Role

Write-Host "Done." -ForegroundColor Green
