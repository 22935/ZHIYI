# Kinlin AI Windows amd64 deployment package

This package supports Windows 11, Docker Desktop in Linux-container mode, and `linux/amd64` only. It does not represent Linux, Kylin, ARM64, or enterprise production acceptance.

The generated package receives the repository's canonical `compose.yaml` plus production and Windows overrides. The template directory intentionally does not keep a second full Compose baseline.

## Start

1. Copy `.env.example` to `.env` and choose a unique `KINLIN_DEPLOYMENT_ID` and free loopback port.
2. Run `powershell -ExecutionPolicy Bypass -File .\start.ps1`.
3. Open `http://127.0.0.1:<KINLIN_HTTP_PORT>`.

`start.ps1` generates missing Secret files under the configured `.secrets` directory, loads `images.tar` only when images are missing, runs Flyway, and starts the five services with `--pull never --no-build`. Only Frontend publishes a host port.

## Operations

- Status: `.\status.ps1`
- Logs: `.\logs.ps1 -Service backend -Follow`
- Stop without deleting data: `.\stop.ps1`
- Backup: `.\backup.ps1 -OutputRoot D:\kinlin-backups`
- Restore into a new isolated deployment: `.\restore.ps1 -Backup D:\kinlin-backups\<backup> -TargetDeploymentId kinlin-restored-001 -TargetHttpPort 8081`

Use `-TargetEnvFile` and `-TargetSecretsDir` to keep restore runtime configuration outside the package directory.

Backup and restore require Python 3 with the standard library; the required Kinlin modules are included under `.kinlin`. Restore refuses an existing target environment file or existing target volumes and never runs `down -v`.

Do not add real Secret values to `.env`, copy `.secrets` into the package, or reuse a `KINLIN_DEPLOYMENT_ID` for unrelated data.
