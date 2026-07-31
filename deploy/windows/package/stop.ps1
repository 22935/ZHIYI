param([string]$EnvFile = ".env")

. (Join-Path $PSScriptRoot ".kinlin\common.ps1")
$context = Read-KinlinPackageEnv $EnvFile
Write-Host "Stopping containers without deleting containers, networks, or named volumes"
Invoke-KinlinPackageCompose $context stop
