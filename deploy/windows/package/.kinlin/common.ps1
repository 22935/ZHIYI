Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$script:KinlinPackageRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Read-KinlinPackageEnv {
    param([string]$EnvFile = ".env")
    $path = if ([IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $script:KinlinPackageRoot $EnvFile }
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Environment file does not exist: $path" }
    $values = @{}
    foreach ($line in Get-Content -LiteralPath $path -Encoding UTF8) {
        $line = $line.Trim()
        if (-not $line -or $line.StartsWith("#")) { continue }
        $parts = $line.Split("=", 2)
        if ($parts.Count -ne 2 -or $parts[0] -notmatch '^[A-Z][A-Z0-9_]*$') { throw "Invalid KEY=value line in $path" }
        if ($parts[0] -ne "KINLIN_SECRETS_DIR" -and $parts[0] -match '(PASSWORD|TOKEN|SECRET|API_?KEY|JWT)') { throw "Sensitive value is forbidden in the environment file: $($parts[0])" }
        $values[$parts[0]] = $parts[1]
    }
    foreach ($required in @("KINLIN_DEPLOYMENT_ID", "KINLIN_SECRETS_DIR")) {
        if (-not $values.ContainsKey($required)) { throw "$required is required in $path" }
    }
    if ($values["KINLIN_DEPLOYMENT_ID"] -notmatch '^[a-z0-9][a-z0-9-]{2,31}$') { throw "Invalid KINLIN_DEPLOYMENT_ID" }
    $secretValue = $values["KINLIN_SECRETS_DIR"]
    $secretPath = if ([IO.Path]::IsPathRooted($secretValue)) { $secretValue } else { Join-Path $script:KinlinPackageRoot $secretValue }
    return [PSCustomObject]@{
        EnvFile = [IO.Path]::GetFullPath($path)
        Values = $values
        DeploymentId = $values["KINLIN_DEPLOYMENT_ID"]
        SecretsDir = [IO.Path]::GetFullPath($secretPath)
        HttpPort = if ($values.ContainsKey("KINLIN_HTTP_PORT")) { [int]$values["KINLIN_HTTP_PORT"] } else { 8080 }
    }
}

function Set-KinlinPackageEnvironment {
    param($Context)
    foreach ($entry in $Context.Values.GetEnumerator()) { [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, "Process") }
    $env:KINLIN_SECRETS_DIR = $Context.SecretsDir
    $env:KINLIN_COMPOSE_FILES = [string]::Join([IO.Path]::PathSeparator, @(
        (Join-Path $script:KinlinPackageRoot "compose.yaml"),
        (Join-Path $script:KinlinPackageRoot "compose.prod.yaml"),
        (Join-Path $script:KinlinPackageRoot "compose.windows.prod.yaml")
    ))
    $env:PYTHONPATH = Join-Path $script:KinlinPackageRoot ".kinlin"
}

function Get-KinlinComposeArguments {
    param($Context)
    return @(
        "-f", (Join-Path $script:KinlinPackageRoot "compose.yaml"),
        "-f", (Join-Path $script:KinlinPackageRoot "compose.prod.yaml"),
        "-f", (Join-Path $script:KinlinPackageRoot "compose.windows.prod.yaml"),
        "--env-file", $Context.EnvFile
    )
}

function Invoke-KinlinPackageCompose {
    param($Context, [Parameter(ValueFromRemainingArguments = $true)][string[]]$ComposeArgs)
    Set-KinlinPackageEnvironment $Context
    $base = Get-KinlinComposeArguments $Context
    Push-Location $script:KinlinPackageRoot
    try {
        & docker compose @base @ComposeArgs
        if ($LASTEXITCODE -ne 0) { throw "Docker Compose failed with exit code $LASTEXITCODE" }
    } finally { Pop-Location }
}

function New-KinlinRandomSecret {
    $bytes = [byte[]]::new(48)
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($bytes) } finally { $generator.Dispose() }
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Initialize-KinlinPackageSecrets {
    param($Context)
    New-Item -ItemType Directory -Path $Context.SecretsDir -Force | Out-Null
    foreach ($name in @("db_admin_password", "db_password", "redis_password", "jwt_secret", "ai_internal_token")) {
        $path = Join-Path $Context.SecretsDir $name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            [IO.File]::WriteAllText($path, (New-KinlinRandomSecret), [Text.UTF8Encoding]::new($false))
        }
    }
    Write-Host "Secret files are ready outside Git at $($Context.SecretsDir)"
}

function Get-KinlinImageReferences {
    param($Context)
    $defaults = [ordered]@{
        KINLIN_FRONTEND_IMAGE = "kinlin-ai/frontend:windows-amd64"
        KINLIN_BACKEND_IMAGE = "kinlin-ai/backend:windows-amd64"
        KINLIN_AI_IMAGE = "kinlin-ai/ai-service:windows-amd64"
        KINLIN_POSTGRES_IMAGE = "kinlin-ai/postgres:windows-amd64"
        KINLIN_REDIS_IMAGE = "kinlin-ai/redis:windows-amd64"
        KINLIN_FLYWAY_IMAGE = "kinlin-ai/flyway:windows-amd64"
    }
    return @($defaults.GetEnumerator() | ForEach-Object { if ($Context.Values.ContainsKey($_.Key)) { $Context.Values[$_.Key] } else { $_.Value } })
}

function Test-KinlinPackageImage {
    param([string]$Reference)
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & docker image inspect $Reference *> $null
        return $LASTEXITCODE -eq 0
    } finally { $ErrorActionPreference = $previousPreference }
}

function Ensure-KinlinPackageImages {
    param($Context)
    $missing = @(Get-KinlinImageReferences $Context | Where-Object { -not (Test-KinlinPackageImage $_) })
    if ($missing.Count -gt 0) {
        $archive = Join-Path $script:KinlinPackageRoot "images.tar"
        if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) { throw "Missing images and images.tar: $($missing -join ', ')" }
        Write-Host "Loading packaged linux/amd64 images"
        & docker load --input $archive
        if ($LASTEXITCODE -ne 0) { throw "docker load failed" }
    }
    foreach ($image in Get-KinlinImageReferences $Context) {
        $architecture = (& docker image inspect $image --format '{{.Architecture}}').Trim()
        if ($LASTEXITCODE -ne 0 -or $architecture -ne "amd64") { throw "Image is missing or not amd64: $image" }
    }
}
