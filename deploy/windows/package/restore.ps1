param(
    [Parameter(Mandatory = $true)][string]$Backup,
    [Parameter(Mandatory = $true)][string]$TargetDeploymentId,
    [int]$TargetHttpPort = 8081,
    [string]$SourceEnvFile = ".env",
    [string]$TargetEnvFile,
    [string]$TargetSecretsDir
)

. (Join-Path $PSScriptRoot ".kinlin\common.ps1")
if ($TargetDeploymentId -notmatch '^[a-z0-9][a-z0-9-]{2,31}$') { throw "Invalid target deployment ID" }
$source = Read-KinlinPackageEnv $SourceEnvFile
if (-not $TargetEnvFile) { $TargetEnvFile = ".env.$TargetDeploymentId" }
$targetPath = if ([IO.Path]::IsPathRooted($TargetEnvFile)) { $TargetEnvFile } else { Join-Path $script:KinlinPackageRoot $TargetEnvFile }
if (Test-Path -LiteralPath $targetPath) { throw "Target environment file already exists: $targetPath" }
$targetSecrets = if ($TargetSecretsDir) {
    if ([IO.Path]::IsPathRooted($TargetSecretsDir)) { [IO.Path]::GetFullPath($TargetSecretsDir) } else { [IO.Path]::GetFullPath((Join-Path $script:KinlinPackageRoot $TargetSecretsDir)) }
} else {
    Join-Path $script:KinlinPackageRoot ".secrets\$TargetDeploymentId"
}

$values = [ordered]@{}
foreach ($entry in $source.Values.GetEnumerator()) { $values[$entry.Key] = $entry.Value }
$values["KINLIN_DEPLOYMENT_ID"] = $TargetDeploymentId
$values["KINLIN_SECRETS_DIR"] = $targetSecrets.Replace('\', '/')
$values["KINLIN_HTTP_PORT"] = [string]$TargetHttpPort
$values["KINLIN_PUBLIC_ORIGIN"] = "http://127.0.0.1:$TargetHttpPort"
$networkSlot = 20 + ($TargetHttpPort % 200)
$values["KINLIN_WEB_SUBNET"] = "10.253.$networkSlot.0/28"
$values["KINLIN_AGENT_SUBNET"] = "10.253.$networkSlot.16/28"
$values["KINLIN_DATA_SUBNET"] = "10.253.$networkSlot.32/28"
$values["KINLIN_INGRESS_SUBNET"] = "10.253.$networkSlot.48/28"
$lines = @("# Generated non-sensitive restore target; Secret values remain in .secrets/.")
$lines += $values.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }
[IO.File]::WriteAllLines([IO.Path]::GetFullPath($targetPath), $lines, [Text.UTF8Encoding]::new($false))

$target = Read-KinlinPackageEnv $targetPath
Initialize-KinlinPackageSecrets $target
Set-KinlinPackageEnvironment $target
Ensure-KinlinPackageImages $target
$backupPath = if ([IO.Path]::IsPathRooted($Backup)) { $Backup } else { Join-Path $script:KinlinPackageRoot $Backup }
& python -m scripts.infra.restore ([IO.Path]::GetFullPath($backupPath)) --target-deployment-id $TargetDeploymentId --secrets-dir $targetSecrets --execute
if ($LASTEXITCODE -ne 0) { throw "Restore failed; source deployment and backup were not modified" }
Invoke-KinlinPackageCompose $target up -d --pull never --no-build --wait
Write-Host "Restored deployment is ready at http://127.0.0.1:$TargetHttpPort"
Write-Host "Use -EnvFile $targetPath for subsequent package commands"
