param(
    [string]$EnvFile = ".env.windows",
    [string]$ConfirmInstanceId
)

. (Join-Path $PSScriptRoot "_common.ps1")
$context = Get-KinlinWindowsContext $EnvFile
Write-KinlinContext $context
Write-Warning "This prunes Docker Desktop's global BuildKit cache older than 168h; it is not scoped to this deployment and does not delete data volumes"
if (-not $ConfirmInstanceId) { $ConfirmInstanceId = Read-Host "Type the deployment ID to confirm the global cache cleanup" }
if ($ConfirmInstanceId -cne $context.DeploymentId) { throw "Instance confirmation mismatch; build cache was not changed" }
& docker builder prune --filter "until=168h" --force
if ($LASTEXITCODE -ne 0) { throw "BuildKit cache prune failed" }
