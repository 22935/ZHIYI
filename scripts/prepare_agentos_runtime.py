#!/usr/bin/env python3
"""Inspect, or explicitly prepare, the existing AgentOS data volume.

Uses the stores' administrative upgrades and the Runtime's OS instance lock.
Never imports app.main, constructs a Runtime, or repairs accepted facts.
"""
from contextlib import closing
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys


ROOT = Path(__file__).resolve().parents[1]
APPS = ROOT / "apps" if (ROOT / "apps" / "agentOS").is_dir() else ROOT
sys.path.insert(0, str(APPS / "agentOS" / "src"))
from support.stores.c2_schema_upgrade import SchemaUpgradeError, inspect_databases, upgrade_databases
from support.stores.execution_dispatch_store import SQLiteExecutionDispatchStore


def instance_lock():
    # Load the existing implementation without importing app.execution's heavy
    # composition-root exports. The cross-process authority is the same OS lock.
    spec = importlib.util.spec_from_file_location(
        "_maintenance_instance_lock", APPS / "agent" / "app" / "execution" / "instance_lock.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inspect_dispatch(path):
    if not path.is_file() or path.stat().st_size == 0:
        return {"status": "UPGRADE_REQUIRED"}
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as conn:
        names = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
            "('execution_dispatch_schema','execution_dispatch_commands')")}
        if not names:
            return {"status": "UPGRADE_REQUIRED"}
        # A partially installed or incompatible journal is not an empty journal.
        SQLiteExecutionDispatchStore.check_schema(conn)
        return {"status": "READY", "version": 1}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for flag, env in (("workflow", "AGENTOS_WORKFLOW_DB_PATH"),
                      ("checkpoint", "AGENTOS_LANGGRAPH_CHECKPOINT_DB"),
                      ("identity", "AGENTOS_IDENTITY_DB")):
        parser.add_argument(f"--{flag}-db", type=Path, default=os.getenv(env),
                            required=not os.getenv(env))
    parser.add_argument("--apply", action="store_true", help="Explicitly upgrade compatible databases")
    parser.add_argument("--initialize-empty", action="store_true", help="Explicitly allow empty database initialization")
    args = parser.parse_args(argv)
    if args.initialize_empty and not args.apply:
        parser.error("--initialize-empty requires --apply")
    # Preserve symlinks for the administrative upgrader's path checks; resolving
    # them here would hide an explicitly forbidden symlink target.
    paths = {role: Path(getattr(args, role + "_db")).absolute()
             for role in ("workflow", "checkpoint", "identity")}
    receipt = {"status": "FAILED", "mode": "apply" if args.apply else "inspect",
               "stage": "preflight", "paths": {key: str(value) for key, value in paths.items()}}
    lock = None
    acquired = False
    code = 1
    try:
        receipt["databases"] = inspect_databases(**paths, initialize_empty=args.initialize_empty)
        if any(item["status"] == "INVALID" for item in receipt["databases"].values()):
            raise SchemaUpgradeError("C2 preflight rejected; inspect database errors; no automatic repair")
        receipt["dispatch"] = inspect_dispatch(paths["workflow"])
        if args.apply:
            receipt["stage"] = "instance_lock"
            lock = instance_lock()
            lock.acquire_workflow_instance_lock(str(paths["workflow"]))
            acquired = True
            # Revalidate the dispatch journal under the same maintenance lock
            # before the first C2 write, including after a concurrent change.
            inspect_dispatch(paths["workflow"])
            receipt["stage"] = "c2_upgrade"
            upgrade_databases(**paths, initialize_empty=args.initialize_empty)
            receipt["stage"] = "dispatch_upgrade"
            SQLiteExecutionDispatchStore.upgrade_schema(paths["workflow"])
            receipt["stage"] = "verification"
            # Re-verify only after the maintenance writes above: the inspect-only
            # path has not touched the databases, so its first pass is already
            # the final verdict and quick_check must not scan every page of the
            # (multi-GB) databases twice per startup.
            receipt["databases"] = inspect_databases(**paths)
            receipt["dispatch"] = inspect_dispatch(paths["workflow"])
        else:
            receipt["stage"] = "verification"
        ready = all(item["status"] == "READY" for item in receipt["databases"].values())
        ready = ready and receipt["dispatch"]["status"] == "READY"
        if ready:
            SQLiteExecutionDispatchStore(paths["workflow"])
        receipt["status"] = "READY" if ready else "NOT_READY"
        code = 0 if ready else 2
    except (SchemaUpgradeError, sqlite3.Error, OSError, RuntimeError, ValueError) as exc:
        receipt["status"] = "FAILED"
        receipt["error"] = str(exc)
        receipt["recovery"] = "Keep these exact databases; inspect and reapply only after resolving the reported cause."
    finally:
        if acquired:
            try:
                lock.release_workflow_instance_lock()
            except Exception as exc:
                receipt.update(status="FAILED", stage="lock_release", error=str(exc))
                code = 1
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
