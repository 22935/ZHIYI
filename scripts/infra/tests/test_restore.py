from pathlib import Path

from scripts.infra import restore


def test_global_restore_omits_only_existing_bootstrap_admin(tmp_path: Path, monkeypatch):
    source = tmp_path / "globals.sql"
    source.write_text(
        "CREATE ROLE kinlin_ai;\n"
        "ALTER ROLE kinlin_ai WITH NOSUPERUSER LOGIN;\n"
        "CREATE ROLE postgres;\n"
        "ALTER ROLE postgres WITH SUPERUSER LOGIN;\n",
        encoding="utf-8",
    )
    captured = {}

    def fake_run(command, **kwargs):
        captured["input"] = kwargs["input"].decode("utf-8")

    monkeypatch.setattr(restore.subprocess, "run", fake_run)
    restore.restore_globals(source, ["psql"], {}, "postgres")

    assert "kinlin_ai" in captured["input"]
    assert "ROLE postgres" not in captured["input"]
