param(
    [ValidateSet("all", "frontend", "backend", "ai-service", "postgres", "redis")]
    [string]$Service = "all",
    [int]$Tail = 200,
    [switch]$Follow,
    [string]$EnvFile = ".env.windows"
)

. (Join-Path $PSScriptRoot "_common.ps1")
$context = Get-KinlinWindowsContext $EnvFile
Write-KinlinContext $context
$secretValues = @(Get-KinlinSecretValues $context)
$composeArgs = Get-KinlinComposeArguments $context
$arguments = @("logs", "--no-color", "--tail", [string]$Tail)
if ($Follow) { $arguments += "--follow" }
if ($Service -ne "all") { $arguments += $Service }
Push-Location $context.ProjectRoot
try {
    & docker compose @composeArgs @arguments 2>&1 | ForEach-Object {
        Protect-KinlinDiagnosticText -Text ([string]$_) -SecretValues $secretValues
    }
    if ($LASTEXITCODE -ne 0) { throw "Unable to read service logs" }
} finally {
    Pop-Location
}
