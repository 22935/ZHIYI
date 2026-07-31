param(
    [string]$EnvFile = ".env.windows",
    [string]$OutputRoot
)

. (Join-Path $PSScriptRoot "_common.ps1")
$context = Get-KinlinWindowsContext $EnvFile
Write-KinlinContext $context
if (-not $OutputRoot) { $OutputRoot = Join-Path $context.ProjectRoot "artifacts\infra-rfc-v1.1\runtime\windows-diagnostics" }
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$output = Join-Path ([System.IO.Path]::GetFullPath($OutputRoot)) "$($context.DeploymentId)-$stamp"
New-Item -ItemType Directory -Path $output -Force | Out-Null
$composeArgs = Get-KinlinComposeArguments $context
$secretValues = @(Get-KinlinSecretValues $context)

function Save-CommandOutput {
    param([string]$Name, [scriptblock]$Command, [switch]$Sanitize)
    try {
        $lines = & $Command 2>&1 | ForEach-Object { [string]$_ }
    } catch {
        $lines = @("CHECK_FAILED: $($_.Exception.Message)")
    }
    if ($Sanitize) {
        $lines = $lines | ForEach-Object { Protect-KinlinDiagnosticText -Text ([string]$_) -SecretValues $secretValues }
    }
    $lines | Set-Content -LiteralPath (Join-Path $output $Name) -Encoding UTF8
}

Save-CommandOutput "docker-version.txt" { docker version }
Save-CommandOutput "compose-version.txt" { docker compose version }
Save-CommandOutput "docker-context.txt" { docker context show }
Save-CommandOutput "wsl-status.txt" { Get-KinlinWslOutput "--status"; Get-KinlinWslOutput "--list --verbose" }
Save-CommandOutput "compose-ps.txt" { Push-Location $context.ProjectRoot; try { docker compose @composeArgs ps } finally { Pop-Location } }
Save-CommandOutput "published-ports.txt" { docker ps --filter "label=com.kinlin.deployment-id=$($context.DeploymentId)" --format 'table {{.Names}}\t{{.Ports}}\t{{.Status}}' }
Save-CommandOutput "networks.txt" { docker network ls --filter "label=com.kinlin.deployment-id=$($context.DeploymentId)"; docker network inspect "$($context.DeploymentId)_web_network_v11" "$($context.DeploymentId)_agent_network_v11" "$($context.DeploymentId)_data_network_v11" "$($context.DeploymentId)_windows_ingress_v11" }
Save-CommandOutput "volumes.txt" { docker volume ls --filter "label=com.kinlin.deployment-id=$($context.DeploymentId)"; docker system df -v }
Save-CommandOutput "health.txt" { docker ps --filter "label=com.kinlin.deployment-id=$($context.DeploymentId)" --format '{{.Names}} {{.Status}}' }
Save-CommandOutput "connectivity.txt" {
    Push-Location $context.ProjectRoot
    try {
        docker compose @composeArgs exec -T frontend wget -qO- http://backend:8080/health/live
        foreach ($hostName in @("ai-service", "postgres", "redis")) {
            docker compose @composeArgs exec -T frontend getent hosts $hostName 2>$null
            Write-Output "frontend_dns_$hostName`_exit=$LASTEXITCODE (expected nonzero)"
        }
        docker compose @composeArgs exec -T backend wget -qO- http://ai-service:8000/health/live
        foreach ($target in @(@("postgres", "5432"), @("redis", "6379"))) {
            $previousErrorPreference = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            docker compose @composeArgs exec -T backend nc -z -w 3 $target[0] $target[1] 2>$null
            $connectExit = $LASTEXITCODE
            $ErrorActionPreference = $previousErrorPreference
            Write-Output "backend_tcp_$($target[0])_$($target[1])_exit=$connectExit (expected zero)"
        }
        docker compose @composeArgs exec -T ai-service python -c "import socket; s=socket.socket(); s.settimeout(3); print('ai_tcp_backend_8080_connect_ex='+str(s.connect_ex(('backend',8080))))"
        foreach ($hostName in @("postgres", "redis")) {
            docker compose @composeArgs exec -T ai-service getent hosts $hostName 2>$null
            Write-Output "ai_dns_$hostName`_exit=$LASTEXITCODE (expected nonzero)"
        }
        Write-Output "External internet connectivity is informational and is not required for local runtime"
        docker compose @composeArgs exec -T ai-service python -c "import urllib.request; print('ai_external_https='+str(urllib.request.urlopen('https://www.example.com',timeout=10).status))" 2>$null
        Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$($context.HttpPort)/" -TimeoutSec 5 | Select-Object StatusCode
    } finally { Pop-Location }
}
Save-CommandOutput "recent-logs-redacted.txt" { Push-Location $context.ProjectRoot; try { docker compose @composeArgs logs --no-color --tail 100 } finally { Pop-Location } } -Sanitize

Write-Host "Diagnostics written to $output"
