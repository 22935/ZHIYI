"""Create a consistent, verified backup of the AgentOS SQLite store."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from agentos.stores.sqlite_workflow_store import SQLiteWorkflowStore


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("destination")
    parser.add_argument("--metadata")
    args = parser.parse_args()
    destination = Path(args.destination).resolve()
    result = SQLiteWorkflowStore(args.source).backup_to(destination)
    result["sha256"] = sha256(destination)
    if args.metadata:
        metadata = Path(args.metadata)
        metadata.parent.mkdir(parents=True, exist_ok=True)
        metadata.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
