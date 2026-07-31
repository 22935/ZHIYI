from __future__ import annotations

import sys

from scripts.infra import init_secrets


def test_init_secrets_migrates_model_key_without_overwriting_it(tmp_path, monkeypatch):
    legacy_env = tmp_path / ".env"
    legacy_env.write_text(
        "DEEPSEEK_API_KEY='first-secret'\n"
        "DASHSCOPE_API_KEY=your-dashscope-key\n",
        encoding="utf-8",
    )
    secret_root = tmp_path / "secrets"

    monkeypatch.setattr(
        sys,
        "argv",
        ["init_secrets", str(secret_root), "--legacy-env-file", str(legacy_env)],
    )
    assert init_secrets.main() == 0
    assert (secret_root / "deepseek_api_key").read_text(encoding="utf-8") == "first-secret\n"
    assert (secret_root / "dashscope_api_key").read_bytes() == b""

    legacy_env.write_text("DEEPSEEK_API_KEY=second-secret\n", encoding="utf-8")
    assert init_secrets.main() == 0
    assert (secret_root / "deepseek_api_key").read_text(encoding="utf-8") == "first-secret\n"

