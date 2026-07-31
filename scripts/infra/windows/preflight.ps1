param(
    [string]$EnvFile = ".env.windows",
    [switch]$Full
)

. (Join-Path $PSScriptRoot "_common.ps1")
$context = Get-KinlinWindowsContext $EnvFile
Write-KinlinContext $context

if ($env:OS -ne "Windows_NT") { throw "P1-Windows preflight requires a Windows host" }
$dockerContext = (& docker context show).Trim()
if ($LASTEXITCODE -ne 0) { throw "Unable to read Docker context" }

$dockerJson = & docker version --format '{{json .}}'
if ($LASTEXITCODE -ne 0) { throw "Docker Engine is unavailable" }
$dockerVersion = $dockerJson | ConvertFrom-Json
if ($dockerVersion.Server.Os -ne "linux") { throw "Docker Desktop must run Linux containers" }
$securityOptions = (& docker info --format '{{json .SecurityOptions}}').ToLowerInvariant()
if ($securityOptions.Contains("rootless") -or $securityOptions.Contains("userns")) { throw "rootless Docker and userns-remap are unsupported" }

$composeVersion = (& docker compose version --short).Trim()
if ($LASTEXITCODE -ne 0) { throw "Docker Compose is unavailable" }
$env:DOCKER_BUILDKIT = "1"
$env:COMPOSE_DOCKER_CLI_BUILD = "1"

if (-not (Test-Path -LiteralPath $context.SecretsDir -PathType Container)) {
    throw "Secret directory does not exist: $($context.SecretsDir)"
}
& python -m scripts.infra.preflight --deployment-id $context.DeploymentId --secrets-dir $context.SecretsDir --bind-address 127.0.0.1
if ($LASTEXITCODE -ne 0) { throw "Canonical infrastructure preflight failed" }

$composeArgs = Get-KinlinComposeArguments $context
Push-Location $context.ProjectRoot
try {
    & docker compose @composeArgs config --quiet
    if ($LASTEXITCODE -ne 0) { throw "Windows Compose merge is invalid" }
    $rendered = & docker compose @composeArgs config --format json
    if ($LASTEXITCODE -ne 0) { throw "Unable to render Windows Compose" }
} finally {
    Pop-Location
}

$modelProviderConfigured = $false
foreach ($name in @("db_admin_password", "db_password", "redis_password", "jwt_secret", "ai_internal_token", "deepseek_api_key", "dashscope_api_key", "tavily_api_key")) {
    $secretPath = Join-Path $context.SecretsDir $name
    $rawSecretValue = Get-Content -LiteralPath $secretPath -Raw -Encoding UTF8
    $secretValue = if ($null -eq $rawSecretValue) { "" } else { ([string]$rawSecretValue).Trim() }
    if ($secretValue -and $rendered.Contains($secretValue)) { throw "Secret value leaked into rendered Compose: $name" }
    if ($name -in @("deepseek_api_key", "dashscope_api_key") -and $secretValue) { $modelProviderConfigured = $true }
}
if (-not $modelProviderConfigured) { Write-Warning "No model provider API Key is configured; local services can start, but real model requests will be unavailable" }

$model = $rendered | ConvertFrom-Json
$frontendNetworks = @($model.services.frontend.networks.PSObject.Properties.Name)
if ($frontendNetworks -notcontains "web-network" -or $frontendNetworks -notcontains "windows-ingress-network") { throw "Frontend network merge is invalid" }
foreach ($service in @("backend", "ai-service", "postgres", "redis")) {
    $serviceModel = $model.services.PSObject.Properties[$service].Value
    $networks = @($serviceModel.networks.PSObject.Properties.Name)
    if ($networks -contains "windows-ingress-network") { throw "$service must not join windows-ingress-network" }
    $portsProperty = $serviceModel.PSObject.Properties["ports"]
    if ($null -ne $portsProperty -and @($portsProperty.Value).Count -gt 0) { throw "$service unexpectedly publishes a host port" }
}

Write-Host "Docker context=$dockerContext, Engine=$($dockerVersion.Server.Version), Compose=$composeVersion, kernel=$($dockerVersion.Server.KernelVersion)"
if ($Full) {
    $computer = Get-CimInstance Win32_ComputerSystem
    $disk = Get-Volume -DriveLetter ([System.IO.Path]::GetPathRoot($context.ProjectRoot).Substring(0, 1))
    $dockerRoot = (& docker info --format '{{.DockerRootDir}}').Trim()
    Write-Host "Host CPU=$($computer.NumberOfLogicalProcessors), memoryBytes=$($computer.TotalPhysicalMemory)"
    Write-Host "Workspace disk freeBytes=$($disk.SizeRemaining), DockerRootDir=$dockerRoot, BuildKit=enabled"
    try {
        Write-Host "WSL status:"
        Write-Host (Get-KinlinWslOutput "--status")
    } catch {
        Write-Warning "WSL status is unavailable: $($_.Exception.Message)"
    }
    Write-Host "Docker disk usage:"
    & docker system df
    if ($LASTEXITCODE -ne 0) { Write-Warning "Docker disk usage could not be collected" }
}
Write-Host "Windows development preflight passed"
