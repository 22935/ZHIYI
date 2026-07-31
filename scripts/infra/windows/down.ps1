param([string]$EnvFile = ".env.windows")

. (Join-Path $PSScriptRoot "_common.ps1")
$context = Get-KinlinWindowsContext $EnvFile
Write-KinlinContext $context
Write-Host "Stopping containers without deleting named volumes"
Invoke-KinlinCompose $context down --remove-orphans
