param([string]$EnvFile = ".env")

. (Join-Path $PSScriptRoot ".kinlin\common.ps1")
$context = Read-KinlinPackageEnv $EnvFile
Invoke-KinlinPackageCompose $context ps
Write-Host "Published host ports (only Frontend is allowed):"
& docker ps --filter "label=com.kinlin.deployment-id=$($context.DeploymentId)" --format 'table {{.Names}}\t{{.Ports}}\t{{.Status}}'
if ($LASTEXITCODE -ne 0) { throw "Unable to inspect deployment ports" }
