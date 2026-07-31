param(
    [string]$OutputRoot = "artifacts\windows",
    [switch]$SkipBuild,
    [switch]$SkipImageExport
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$outputBase = if ([IO.Path]::IsPathRooted($OutputRoot)) { $OutputRoot } else { Join-Path $projectRoot $OutputRoot }
$output = Join-Path ([IO.Path]::GetFullPath($outputBase)) "kinlin-ai-windows-amd64"
if (Test-Path -LiteralPath $output) { throw "Refusing to overwrite an existing deployment package: $output" }

$gitSha = (& git -C $projectRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw "Unable to read source commit" }
$created = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$env:VERSION = "windows-amd64"
$env:GIT_SHA = $gitSha
$env:CREATED = $created

function Test-KinlinImage {
    param([string]$Reference)
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & docker image inspect $Reference *> $null
        return $LASTEXITCODE -eq 0
    } finally { $ErrorActionPreference = $previousPreference }
}

if (-not $SkipBuild) {
    Push-Location $projectRoot
    try {
        & docker buildx bake -f docker-bake.hcl frontend backend ai-service postgres redis `
            --set frontend.platform=linux/amd64 `
            --set backend.platform=linux/amd64 `
            --set ai-service.platform=linux/amd64 `
            --set postgres.platform=linux/amd64 `
            --set redis.platform=linux/amd64 `
            --load
        if ($LASTEXITCODE -ne 0) { throw "Windows amd64 image build failed" }
    } finally { Pop-Location }
}

$flyway = "kinlin-ai/flyway:windows-amd64"
if (-not (Test-KinlinImage $flyway)) {
    if (Test-KinlinImage "kinlin-ai-flyway:dev") {
        & docker tag "kinlin-ai-flyway:dev" $flyway
    } else {
        Push-Location $projectRoot
        try {
            & docker build --platform linux/amd64 --tag $flyway .\docker\flyway
            if ($LASTEXITCODE -ne 0) { throw "Flyway amd64 image is unavailable" }
        } finally { Pop-Location }
    }
}

$images = @(
    "kinlin-ai/frontend:windows-amd64",
    "kinlin-ai/backend:windows-amd64",
    "kinlin-ai/ai-service:windows-amd64",
    "kinlin-ai/postgres:windows-amd64",
    "kinlin-ai/redis:windows-amd64",
    $flyway
)
foreach ($image in $images) {
    $architecture = (& docker image inspect $image --format '{{.Architecture}}').Trim()
    if ($LASTEXITCODE -ne 0 -or $architecture -ne "amd64") { throw "Required linux/amd64 image is missing: $image" }
}

$runtimeData = & docker run --rm --user 0 --entrypoint sh "kinlin-ai/ai-service:windows-amd64" -c "find /app -type f \( -name '*.db' -o -name '*.sqlite' -o -name '*.sqlite3' -o -name '*.rdb' \) -print"
if ($LASTEXITCODE -ne 0) { throw "Unable to inspect AI image for runtime data" }
if ($runtimeData) { throw "AI image contains forbidden runtime data: $runtimeData" }

New-Item -ItemType Directory -Path $output -Force | Out-Null
$template = Join-Path $projectRoot "deploy\windows\package"
foreach ($item in Get-ChildItem -LiteralPath $template -Force) {
    Copy-Item -LiteralPath $item.FullName -Destination $output -Recurse
}
Copy-Item -LiteralPath (Join-Path $projectRoot "compose.yaml") -Destination (Join-Path $output "compose.yaml")
Copy-Item -LiteralPath (Join-Path $projectRoot "compose.prod.yaml") -Destination (Join-Path $output "compose.prod.yaml")
Copy-Item -LiteralPath (Join-Path $projectRoot "compose.windows.prod.yaml") -Destination (Join-Path $output "compose.windows.prod.yaml")
Copy-Item -LiteralPath (Join-Path $projectRoot "backend\src\main\resources\db\migration") -Destination (Join-Path $output "migrations") -Recurse

$infraTarget = Join-Path $output ".kinlin\scripts\infra"
New-Item -ItemType Directory -Path $infraTarget -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $projectRoot "scripts\__init__.py") -Destination (Join-Path $output ".kinlin\scripts\__init__.py")
foreach ($name in @("__init__.py", "common.py", "backup.py", "restore.py", "schema_audit.py")) {
    Copy-Item -LiteralPath (Join-Path $projectRoot "scripts\infra\$name") -Destination (Join-Path $infraTarget $name)
}
[IO.File]::WriteAllText((Join-Path $output ".kinlin\SOURCE_COMMIT"), $gitSha, [Text.UTF8Encoding]::new($false))

if (-not $SkipImageExport) {
    & docker save --output (Join-Path $output "images.tar") @images
    if ($LASTEXITCODE -ne 0) { throw "docker save failed; incomplete package retained for diagnosis" }
}

$forbidden = @()
foreach ($file in Get-ChildItem -LiteralPath $output -Recurse -Force -File) {
    $relative = $file.FullName.Substring($output.TrimEnd('\').Length).TrimStart('\').Replace('\', '/')
    if ($relative -eq ".env.example" -or $relative -eq "images.tar") { continue }
    if ($relative -match '(^|/)(\.env($|\.)|\.secrets|node_modules|target|venv|\.venv|uploads|tests?)(/|$)' -or $relative -match '(?i)\.(db|sqlite|sqlite3|rdb)$') {
        $forbidden += $relative
    }
}
if ($forbidden.Count -gt 0) { throw "Forbidden deployment-package content: $($forbidden -join ', ')" }

if (-not $SkipImageExport) {
    $hash = (Get-FileHash (Join-Path $output "images.tar") -Algorithm SHA256).Hash.ToLowerInvariant()
    [IO.File]::WriteAllText((Join-Path $output ".kinlin\images.sha256"), "$hash  images.tar`n", [Text.UTF8Encoding]::new($false))
}
Write-Host "Windows amd64 deployment package: $output"
