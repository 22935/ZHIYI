param(
    [string]$EnvFile = ".env",
    [string]$OutputRoot = "backups"
)

. (Join-Path $PSScriptRoot ".kinlin\common.ps1")
$context = Read-KinlinPackageEnv $EnvFile
Set-KinlinPackageEnvironment $context
Ensure-KinlinPackageImages $context
$outputPath = if ([IO.Path]::IsPathRooted($OutputRoot)) { $OutputRoot } else { Join-Path $script:KinlinPackageRoot $OutputRoot }
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
$schemaReport = Join-Path ([IO.Path]::GetTempPath()) "kinlin-$($context.DeploymentId)-schema-audit.json"
$base = Get-KinlinComposeArguments $context
$postgresId = (& docker compose @base ps -q postgres).Trim()
if ($LASTEXITCODE -ne 0 -or -not $postgresId) { throw "PostgreSQL is not running" }
$dbUser = if ($context.Values.ContainsKey("KINLIN_DB_USER")) { $context.Values["KINLIN_DB_USER"] } else { "kinlin_ai" }
$dbName = if ($context.Values.ContainsKey("KINLIN_DB_NAME")) { $context.Values["KINLIN_DB_NAME"] } else { "kinlin_ai" }
$dbAdmin = if ($context.Values.ContainsKey("KINLIN_DB_ADMIN_USER")) { $context.Values["KINLIN_DB_ADMIN_USER"] } else { "postgres" }
& python -m scripts.infra.schema_audit --container $postgresId --user $dbUser --database $dbName --deployment-id $context.DeploymentId --output $schemaReport
if ($LASTEXITCODE -ne 0) { throw "Schema audit failed; backup was not started" }

Invoke-KinlinPackageCompose $context stop frontend backend ai-service
try {
    & python -m scripts.infra.backup --deployment-id $context.DeploymentId --database $dbName --app-db-user $dbUser --db-admin-user $dbAdmin --output-root ([IO.Path]::GetFullPath($outputPath)) --schema-report $schemaReport --maintenance-confirmed
    if ($LASTEXITCODE -ne 0) { throw "Backup failed" }
} finally {
    Invoke-KinlinPackageCompose $context up -d --pull never --no-build --wait
    Remove-Item -LiteralPath $schemaReport -Force -ErrorAction SilentlyContinue
}
