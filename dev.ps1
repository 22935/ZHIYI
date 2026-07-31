param(
    [ValidateSet("up", "down", "build", "restart", "logs", "status", "diagnose")]
    [string]$Action = "up",
    [string]$EnvFile = ".env.windows",
    [switch]$DebugPorts,
    [switch]$Build,
    [ValidateSet("frontend", "backend", "ai-service", "postgres", "redis")]
    [string]$BuildService
)

$ErrorActionPreference = "Stop"
$windowsScripts = Join-Path $PSScriptRoot "scripts\infra\windows"

function Invoke-WindowsUp {
    param([switch]$ForceBuild)
    $parameters = @{ EnvFile = $EnvFile }
    if ($DebugPorts) { $parameters.DebugPorts = $true }
    if ($BuildService) {
        if ($Build) { throw "Use either -Build or -BuildService, not both" }
        $parameters.BuildService = $BuildService
    } elseif ($Build -or $ForceBuild) {
        $parameters.Build = $true
    }
    & (Join-Path $windowsScripts "up.ps1") @parameters
}

switch ($Action) {
    "up" { Invoke-WindowsUp }
    "down" { & (Join-Path $windowsScripts "down.ps1") -EnvFile $EnvFile }
    "build" { Invoke-WindowsUp -ForceBuild }
    "restart" {
        & (Join-Path $windowsScripts "down.ps1") -EnvFile $EnvFile
        Invoke-WindowsUp
    }
    "logs" { & (Join-Path $windowsScripts "logs.ps1") -EnvFile $EnvFile -Follow }
    "status" { & (Join-Path $windowsScripts "status.ps1") -EnvFile $EnvFile }
    "diagnose" { & (Join-Path $windowsScripts "diagnose.ps1") -EnvFile $EnvFile }
}
