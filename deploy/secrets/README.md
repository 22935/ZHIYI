# Secret initialization

The release package never contains Secret values. Create an external directory owned by the deployment administrator with these UTF-8 files, each ending in one LF:

- `db_admin_password` (at least 16 characters)
- `db_password` (at least 16 characters)
- `redis_password` (at least 16 characters)
- `jwt_secret` (at least 64 characters)
- `ai_internal_token` (at least 64 characters)
- `deepseek_api_key` (optional; leave empty when DeepSeek is not the system model provider)
- `dashscope_api_key` (optional; leave empty when DashScope/Qwen is not the system model provider)

Use `scripts/init-secrets.sh <external-directory>` for a new installation. Do not rerun it for an existing deployment because rotating these values requires a coordinated procedure.

Configure at least one model API Key to enable the server-managed chat model. Keep the other optional provider file empty. The API Key files are mounted only into the AI service and are never rendered into the Compose environment.
