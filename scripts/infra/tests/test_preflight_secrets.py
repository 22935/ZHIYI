from pathlib import Path

import pytest

from scripts.infra.preflight import OPTIONAL_FILE_SECRETS, REQUIRED_SECRETS, validate_secret_files


def write_secret(root: Path, name: str, value: str) -> None:
    (root / name).write_bytes((value + "\n").encode("utf-8"))


def valid_secret_directory(root: Path) -> None:
    root.mkdir(exist_ok=True)
    for name in REQUIRED_SECRETS:
        size = 64 if name in {"jwt_secret", "ai_internal_token"} else 16
        write_secret(root, name, "x" * size)
    for name in OPTIONAL_FILE_SECRETS:
        (root / name).write_bytes(b"")


def test_optional_model_secret_files_may_be_empty(tmp_path: Path):
    valid_secret_directory(tmp_path)

    states = validate_secret_files(tmp_path)

    assert all(states[name] == "empty" for name in OPTIONAL_FILE_SECRETS)


def test_optional_model_secret_files_must_exist(tmp_path: Path):
    valid_secret_directory(tmp_path)
    (tmp_path / "deepseek_api_key").unlink()

    with pytest.raises(ValueError, match="deepseek_api_key"):
        validate_secret_files(tmp_path)


def test_configured_model_secret_must_be_canonical(tmp_path: Path):
    valid_secret_directory(tmp_path)
    (tmp_path / "deepseek_api_key").write_bytes(b"model-key")

    with pytest.raises(ValueError, match="deepseek_api_key"):
        validate_secret_files(tmp_path)
