param(
    [ValidateSet("all", "frontend", "backend", "ai-service", "postgres", "redis")][string]$Service = "all",
    [int]$Tail = 200,
    [switch]$Follow,
    [string]$EnvFile = ".env"
)

. (Join-Path $PSScriptRoot ".kinlin\common.ps1")
$context = Read-KinlinPackageEnv $EnvFile
$arguments = @("logs", "--no-color", "--tail", [string]$Tail)
if ($Follow) { $arguments += "--follow" }
if ($Service -ne "all") { $arguments += $Service }
$base = Get-KinlinComposeArguments $context
Push-Location $script:KinlinPackageRoot
try {
    & docker compose @base @arguments 2>&1 | ForEach-Object {
        if ($_ -match '(?i)(password|secret|token|api[_-]?key|authorization)') { "[REDACTED SENSITIVE LOG LINE]" } else { $_ }
    }
    if ($LASTEXITCODE -ne 0) { throw "Unable to read deployment logs" }
} finally { Pop-Location }
