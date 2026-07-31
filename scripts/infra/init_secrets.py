#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import secrets
from pathlib import Path


MODEL_SECRET_ENV_NAMES = {
    "deepseek_api_key": "DEEPSEEK_API_KEY",
    "dashscope_api_key": "DASHSCOPE_API_KEY",
    "tavily_api_key": "TAVILY_API_KEY",
}


def read_legacy_model_secrets(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    if not path.is_file():
        raise SystemExit(f"legacy environment file does not exist: {path}")

    imported: dict[str, str] = {}
    expected = {environment: filename for filename, environment in MODEL_SECRET_ENV_NAMES.items()}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, raw_value = line.partition("=")
        if not separator or key.strip() not in expected:
            continue
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if value and not value.lower().startswith(("your-", "replace-", "example-")):
            imported[expected[key.strip()]] = value
    return imported


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory")
    parser.add_argument(
        "--legacy-env-file",
        type=Path,
        help="migrate DEEPSEEK_API_KEY/DASHSCOPE_API_KEY without printing their values",
    )
    args = parser.parse_args()
    root = Path(args.directory)
    root.mkdir(parents=True, exist_ok=True)
    imported_model_secrets = read_legacy_model_secrets(args.legacy_env_file)
    values = {
        "db_admin_password": secrets.token_urlsafe(32),
        "db_password": secrets.token_urlsafe(32),
        "redis_password": secrets.token_urlsafe(32),
        "jwt_secret": secrets.token_urlsafe(64),
        "ai_internal_token": secrets.token_urlsafe(64),
    }
    for name, value in values.items():
        path = root / name
        if not path.exists():
            path.write_bytes((value + "\n").encode("utf-8"))
            if os.name != "nt":
                path.chmod(0o600)
        else:
            existing = path.read_text(encoding="utf-8").strip()
            if not existing or "\n" in existing or "\r" in existing:
                raise SystemExit(f"refusing to normalize malformed secret file: {path}")
            path.write_bytes((existing + "\n").encode("utf-8"))
    for name in MODEL_SECRET_ENV_NAMES:
        path = root / name
        imported = imported_model_secrets.get(name, "")
        if path.exists():
            existing = path.read_text(encoding="utf-8").strip()
            if "\n" in existing or "\r" in existing:
                raise SystemExit(f"refusing to normalize malformed secret file: {path}")
            value = existing or imported
        else:
            value = imported
        path.write_bytes(((value + "\n") if value else "").encode("utf-8"))
        if os.name != "nt":
            path.chmod(0o600)
    if os.name != "nt":
        root.chmod(0o700)
    print(root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
