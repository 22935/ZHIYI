param(
    [string]$EnvFile = ".env.windows",
    [string]$ConfirmInstanceId,
    [switch]$IUnderstandDevelopmentCacheWillBeDeleted
)

. (Join-Path $PSScriptRoot "_common.ps1")
$context = Get-KinlinWindowsContext $EnvFile
Write-KinlinContext $context
if (-not $IUnderstandDevelopmentCacheWillBeDeleted) {
    throw "Pass -IUnderstandDevelopmentCacheWillBeDeleted to enable Backend source cache deletion"
}
if (-not $ConfirmInstanceId) { $ConfirmInstanceId = Read-Host "Type the exact deployment ID" }
if ($ConfirmInstanceId -cne $context.DeploymentId) { throw "Instance confirmation mismatch; cache was not deleted" }

$running = & docker ps --filter "label=com.kinlin.deployment-id=$($context.DeploymentId)" -q
if ($running) { throw "Deployment containers are still running; stop them before deleting the Backend source cache" }

$volumeName = "$($context.DeploymentId)_backend_source_cache"
$existingVolume = @(& docker volume ls --filter "name=^$([regex]::Escape($volumeName))$" --format '{{.Name}}') | Where-Object { $_ -eq $volumeName }
if (-not $existingVolume) {
    Write-Host "Backend source cache does not exist: $volumeName"
    return
}
$inspectOutput = @(& docker volume inspect $volumeName)
if ($LASTEXITCODE -ne 0) { throw "Unable to inspect Backend source cache: $volumeName" }
$volume = ($inspectOutput -join "`n") | ConvertFrom-Json
if ($volume.Name -ne $volumeName) { throw "Unexpected cache volume name: $($volume.Name)" }
if ($volume.Labels.'com.kinlin.deployment-id' -ne $context.DeploymentId) { throw "Backend source cache deployment label mismatch" }
if ($volume.Labels.'com.kinlin.lifecycle' -ne "p1-windows-development-cache") { throw "Backend source cache lifecycle label mismatch" }

& docker volume rm $volumeName
if ($LASTEXITCODE -ne 0) { throw "Failed to remove Backend source cache: $volumeName" }
Write-Host "Removed rebuildable Backend source cache: $volumeName"
