param([string]$EnvFile = ".env")

. (Join-Path $PSScriptRoot ".kinlin\common.ps1")
$context = Read-KinlinPackageEnv $EnvFile
Initialize-KinlinPackageSecrets $context
Ensure-KinlinPackageImages $context
Invoke-KinlinPackageCompose $context config --quiet
Invoke-KinlinPackageCompose $context up -d --pull never --no-build --wait postgres redis ai-service
Invoke-KinlinPackageCompose $context --profile migration run --rm --pull never schema-tool migrate
Invoke-KinlinPackageCompose $context up -d --pull never --no-build --wait
Write-Host "Kinlin AI is ready at http://127.0.0.1:$($context.HttpPort)"
