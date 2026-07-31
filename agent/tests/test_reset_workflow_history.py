from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "reset_workflow_history.py"
SPEC = importlib.util.spec_from_file_location("reset_workflow_history", SCRIPT)
assert SPEC and SPEC.loader
reset = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reset)


def _fixture(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Path]:
    database = tmp_path / "data" / "agentos" / "workflows.sqlite3"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as conn:
        conn.execute(
            "CREATE TABLE tasks (task_id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE runs (run_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, payload TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO tasks VALUES ('task_1', '{}', 'now')")
        conn.execute("INSERT INTO tasks VALUES ('task_orphan', '{}', 'now')")
        conn.execute("INSERT INTO runs VALUES ('run_1', 'task_1', '{}', 'now')")
    material_root = tmp_path / "data" / "task-materials"
    material_dir = material_root / ("mat_" + "a" * 32)
    material_dir.mkdir(parents=True)
    source = material_dir / "source.txt"
    source.write_text("original", encoding="utf-8")
    (material_dir / "metadata.json").write_text(
        json.dumps(
            {
                "materialId": material_dir.name,
                "state": "bound",
                "sourceFile": source.name,
                "bindings": [{"taskId": "task_1", "runId": "run_1"}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(reset.DATABASE_ENV, str(database))
    monkeypatch.setenv(reset.MATERIAL_ROOT_ENV, str(material_root))
    return database, material_root, source


def _counts(database: Path) -> tuple[int, int]:
    with sqlite3.connect(database) as conn:
        return (
            int(conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]),
            int(conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]),
        )


def test_dry_run_is_default_and_does_not_modify_history(tmp_path, monkeypatch, capsys):
    database, _, _ = _fixture(tmp_path, monkeypatch)

    assert reset.main([]) == 0

    assert _counts(database) == (1, 2)
    output = capsys.readouterr().out
    assert "Run: 1" in output
    assert "Task: 2" in output
    assert "Orphan Task: 1" in output
    assert "Material Binding: 1" in output
    assert "integrity_check: ok" in output


def test_execute_clears_history_and_bindings_but_preserves_source(tmp_path, monkeypatch):
    database, material_root, source = _fixture(tmp_path, monkeypatch)

    assert reset.main(["--execute"]) == 0
    assert _counts(database) == (0, 0)
    metadata = json.loads(next(material_root.glob("mat_*/metadata.json")).read_text(encoding="utf-8"))
    assert metadata["bindings"] == []
    assert metadata["state"] == "ready"
    assert source.read_text(encoding="utf-8") == "original"

    assert reset.main(["--execute"]) == 0
    assert _counts(database) == (0, 0)


def test_database_reset_rolls_back_as_one_transaction(tmp_path, monkeypatch):
    database, _, _ = _fixture(tmp_path, monkeypatch)
    with sqlite3.connect(database) as conn:
        conn.execute(
            """
            CREATE TRIGGER prevent_task_delete BEFORE DELETE ON tasks
            BEGIN SELECT RAISE(ABORT, 'blocked'); END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="blocked"):
        reset.main(["--execute"])

    assert _counts(database) == (1, 2)


def test_dry_run_and_execute_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        reset.main(["--dry-run", "--execute"])
