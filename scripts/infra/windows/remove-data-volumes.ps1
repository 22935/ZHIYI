param(
    [string]$EnvFile = ".env.windows",
    [string]$ConfirmInstanceId,
    [switch]$IUnderstandDataWillBeDeleted
)

. (Join-Path $PSScriptRoot "_common.ps1")
$context = Get-KinlinWindowsContext $EnvFile
Write-KinlinContext $context
if (-not $IUnderstandDataWillBeDeleted) { throw "Pass -IUnderstandDataWillBeDeleted to enable the destructive confirmation flow" }
if (-not $ConfirmInstanceId) { $ConfirmInstanceId = Read-Host "DESTRUCTIVE: type the exact deployment ID" }
if ($ConfirmInstanceId -cne $context.DeploymentId) { throw "Instance confirmation mismatch; no volume was removed" }

$running = & docker ps --filter "label=com.kinlin.deployment-id=$($context.DeploymentId)" -q
if ($running) { throw "Deployment containers are still running; stop them before deleting development volumes" }
$candidateVolumes = & docker volume ls --filter "label=com.kinlin.deployment-id=$($context.DeploymentId)" --format '{{.Name}}'
$volumes = @()
foreach ($volume in $candidateVolumes) {
    $actualLabel = (& docker volume inspect $volume --format '{{ index .Labels "com.kinlin.deployment-id" }}').Trim()
    if ($actualLabel -ne $context.DeploymentId) { throw "Volume label mismatch: $volume" }
    $lifecycle = (& docker volume inspect $volume --format '{{ index .Labels "com.kinlin.lifecycle" }}').Trim()
    if ($lifecycle -eq "p1-windows-development-cache") {
        Write-Host "Preserving explicit development cache volume: $volume"
        continue
    }
    $volumes += $volume
}
foreach ($volume in $volumes) {
    & docker volume rm $volume
    if ($LASTEXITCODE -ne 0) { throw "Failed to remove development volume: $volume" }
}
