param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("frontend", "backend", "ai-service", "postgres", "redis")]
    [string]$Service,
    [string]$EnvFile = ".env.windows",
    [switch]$FullRestart
)

. (Join-Path $PSScriptRoot "_common.ps1")
$context = Get-KinlinWindowsContext $EnvFile
Write-KinlinContext $context
if ($Service -eq "backend" -and -not $FullRestart) {
    $totalStopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $syncStopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $syncOutput = @(Invoke-KinlinComposeOutput $context exec -T backend /usr/local/bin/kinlin-sync-backend-source)
    $syncStopwatch.Stop()
    foreach ($line in $syncOutput) { Write-Host $line }
    $resultLine = @($syncOutput | Where-Object { $_ -match '^KINLIN_SOURCE_SYNC_RESULT=(unchanged|changed|deleted)$' }) | Select-Object -Last 1
    if (-not $resultLine) { throw "Backend source sync did not return a recognized result" }
    $syncResult = ($resultLine -split "=", 2)[1]

    $compileSeconds = 0.0
    $reloadSeconds = 0.0
    if ($syncResult -eq "unchanged") {
        Write-Host "Backend source is unchanged; skipping Maven compile"
        Wait-KinlinServiceHealthy $context backend -TimeoutSeconds 30
    } else {
        $reloadSinceUtc = [DateTime]::UtcNow
        $compileStopwatch = [System.Diagnostics.Stopwatch]::StartNew()
        Write-Host "Compiling Backend without tests; Spring Boot DevTools will restart the application"
        Invoke-KinlinCompose $context exec -T --user 10001:10001 backend mvn -B -ntp -DskipTests compile
        $compileStopwatch.Stop()
        $compileSeconds = $compileStopwatch.Elapsed.TotalSeconds

        $reloadStopwatch = [System.Diagnostics.Stopwatch]::StartNew()
        $deadline = (Get-Date).AddSeconds(120)
        $containerId = Get-KinlinServiceContainerId $context backend
        $sinceArgument = $reloadSinceUtc.ToString("o")
        $reloadObserved = $false
        do {
            $recentLogs = @(& docker logs --since $sinceArgument $containerId 2>&1)
            if ($LASTEXITCODE -ne 0) { throw "Unable to read Backend reload logs" }
            if (($recentLogs -join "`n") -match 'Started KinlinAiApplication') {
                & docker exec --user 10001:10001 $containerId sh -c 'address=$(cat /tmp/backend-listen-address); wget -qO- "http://$address:8080/health/ready" >/dev/null'
                if ($LASTEXITCODE -eq 0) {
                    $reloadObserved = $true
                    break
                }
            }
            Start-Sleep -Seconds 1
        } while ((Get-Date) -lt $deadline)
        if (-not $reloadObserved) { throw "Backend DevTools reload did not become ready within 120s" }
        $reloadStopwatch.Stop()
        $reloadSeconds = $reloadStopwatch.Elapsed.TotalSeconds
    }
    $totalStopwatch.Stop()
    Write-Host ("Backend feedback result={0} sync={1:N2}s compile={2:N2}s reloadReady={3:N2}s total={4:N2}s" -f $syncResult, $syncStopwatch.Elapsed.TotalSeconds, $compileSeconds, $reloadSeconds, $totalStopwatch.Elapsed.TotalSeconds)
} else {
    Invoke-KinlinCompose $context restart $Service
    Wait-KinlinServiceHealthy $context $Service
}
Invoke-KinlinCompose $context ps $Service
