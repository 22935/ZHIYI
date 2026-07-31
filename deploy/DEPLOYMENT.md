# Kinlin AI offline deployment

This package installs one architecture and never downloads images. Keep the package, the external deployment environment, the external Secret directory, retained release directories, and verified backups separate.

1. Run `scripts/preflight.sh`.
2. For a new deployment, create external Secret files with `scripts/init-secrets.sh`, create `/etc/kinlin-ai/deployment.env` from `config/.env.prod.example`, then run `scripts/install.sh`.
3. For an upgrade, retain the current release and run the new package's `scripts/upgrade.sh`. It performs preflight, backup, image import, Flyway migration, readiness, smoke, then switches `current`.
4. Use `scripts/rollback.sh --to VERSION` only when the release manifest declares schema rollback compatibility. It never performs destructive Compose teardown, removes volumes, or reverses migrations.
5. `scripts/restore.sh BACKUP NEW_DEPLOYMENT_ID NEW_SECRET_DIRECTORY` restores only into a new deployment ID and new volumes, using separately prepared target Secrets.

`P3_ARM64_NATIVE_RUNTIME` remains unverified until this package passes the same flow on a native arm64 Linux/Kylin host.
