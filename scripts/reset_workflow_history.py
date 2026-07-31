"""Development-only reset for persisted Workflow Run history."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, TextIO


DATABASE_ENV = "AGENTOS_WORKFLOW_DB_PATH"
MATERIAL_ROOT_ENV = "AGENTOS_TASK_MATERIAL_ROOT"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect or clear development Workflow Run history."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Only print counts (default).")
    mode.add_argument("--execute", action="store_true", help="Permanently clear history.")
    return parser


def _database_path() -> Path:
    raw = os.getenv(DATABASE_ENV, "").strip()
    if not raw:
        raise RuntimeError(f"{DATABASE_ENV} is required")
    path = Path(raw).expanduser().resolve()
    if not path.is_file():
        raise RuntimeError(f"workflow database does not exist: {path}")
    return path


def _material_root(database: Path) -> Path:
    configured = os.getenv(MATERIAL_ROOT_ENV, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return database.parent.parent / "task-materials"


def _database_counts(conn: sqlite3.Connection) -> dict[str, int | str]:
    return {
        "runs": int(conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]),
        "tasks": int(conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]),
        "orphanTasks": int(
            conn.execute(
                """
                SELECT COUNT(*) FROM tasks t
                WHERE NOT EXISTS (SELECT 1 FROM runs r WHERE r.task_id = t.task_id)
                """
            ).fetchone()[0]
        ),
        "integrityCheck": str(conn.execute("PRAGMA integrity_check").fetchone()[0]),
    }


def _material_counts(root: Path) -> dict[str, int]:
    materials = 0
    bindings = 0
    if root.is_dir():
        for metadata_path in root.glob("mat_*/metadata.json"):
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            materials += 1
            bindings += len(metadata.get("bindings") or [])
    return {"materials": materials, "materialBindings": bindings}


def inspect_history(database: Path, material_root: Path) -> dict[str, int | str]:
    with sqlite3.connect(database) as conn:
        counts = _database_counts(conn)
    return counts | _material_counts(material_root)


@contextmanager
def _exclusive_runtime_lock(database: Path) -> Iterator[TextIO]:
    lock_path = database.parent / "runtime.instance.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        handle.seek(0)
        if handle.read(1) == "":
            handle.seek(0)
            handle.write("0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError(
                "AI service is still using the workflow database; stop it before --execute"
            ) from exc
        yield handle
    finally:
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        handle.close()


def reset_database(database: Path) -> None:
    with sqlite3.connect(database, timeout=1) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("DELETE FROM runs")
            conn.execute(
                "DELETE FROM tasks WHERE NOT EXISTS "
                "(SELECT 1 FROM runs r WHERE r.task_id = tasks.task_id)"
            )
            run_count = int(conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0])
            orphan_tasks = int(
                conn.execute(
                    """
                    SELECT COUNT(*) FROM tasks t
                    WHERE NOT EXISTS (SELECT 1 FROM runs r WHERE r.task_id = t.task_id)
                    """
                ).fetchone()[0]
            )
            if run_count or orphan_tasks:
                raise RuntimeError("workflow history reset left run or task references")
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def clean_dangling_material_bindings(root: Path, valid_run_ids: set[str]) -> int:
    removed = 0
    if not root.is_dir():
        return removed
    for metadata_path in root.glob("mat_*/metadata.json"):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        bindings = list(metadata.get("bindings") or [])
        retained = [
            binding
            for binding in bindings
            if str(binding.get("runId") or "") in valid_run_ids
        ]
        if retained == bindings:
            continue
        removed += len(bindings) - len(retained)
        metadata["bindings"] = retained
        metadata["state"] = "bound" if retained else "ready"
        temporary = metadata_path.with_name(f".{metadata_path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(
            json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        os.replace(temporary, metadata_path)
    return removed


def _print_counts(label: str, counts: dict[str, int | str]) -> None:
    print(label)
    print(f"  Run: {counts['runs']}")
    print(f"  Task: {counts['tasks']}")
    print(f"  Orphan Task: {counts['orphanTasks']}")
    print(f"  Material: {counts['materials']}")
    print(f"  Material Binding: {counts['materialBindings']}")
    print(f"  integrity_check: {counts['integrityCheck']}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    database = _database_path()
    material_root = _material_root(database)
    before = inspect_history(database, material_root)
    _print_counts("Workflow history dry-run:" if not args.execute else "Before reset:", before)
    if not args.execute:
        return 0

    with _exclusive_runtime_lock(database):
        reset_database(database)
        with sqlite3.connect(database) as conn:
            valid_run_ids = {
                str(row[0]) for row in conn.execute("SELECT run_id FROM runs").fetchall()
            }
        removed_bindings = clean_dangling_material_bindings(material_root, valid_run_ids)
    after = inspect_history(database, material_root)
    _print_counts("After reset:", after)
    print(f"  Removed dangling material bindings: {removed_bindings}")
    if str(after["integrityCheck"]).lower() != "ok":
        raise RuntimeError(f"SQLite integrity_check failed: {after['integrityCheck']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"reset failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
