param([string]$EnvFile = ".env.windows")

. (Join-Path $PSScriptRoot "_common.ps1")
$context = Get-KinlinWindowsContext $EnvFile
Write-KinlinContext $context
Invoke-KinlinCompose $context ps
Write-Host "Container ports and host bindings for this deployment (only host_ip:host_port is published):"
& docker ps --filter "label=com.kinlin.deployment-id=$($context.DeploymentId)" --format 'table {{.Names}}\t{{.Ports}}\t{{.Status}}'
if ($LASTEXITCODE -ne 0) { throw "Unable to inspect published ports" }
