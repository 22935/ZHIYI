"""Convert a pip --report JSON file into a target-platform hash lock."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: lock_from_pip_report.py REPORT OUTPUT")
    report_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    packages: list[tuple[str, str, list[str]]] = []
    for item in report.get("install") or []:
        metadata = item.get("metadata") or {}
        name = canonical_name(str(metadata.get("name") or ""))
        version = str(metadata.get("version") or "")
        archive = (item.get("download_info") or {}).get("archive_info") or {}
        hashes = archive.get("hashes") or {}
        sha256 = hashes.get("sha256")
        if not sha256:
            legacy = str(archive.get("hash") or "")
            if legacy.startswith("sha256="):
                sha256 = legacy.split("=", 1)[1]
        if not name or not version or not sha256:
            raise RuntimeError(f"pip report entry is not lockable: {metadata.get('name')}")
        packages.append((name, version, [str(sha256)]))
    packages.sort(key=lambda item: item[0])
    lines = [
        "# Generated inside the target Linux/Python Docker image from pip --dry-run --report.",
        "# This lock intentionally contains hashes for target-platform binary wheels only.",
        "",
    ]
    for name, version, hashes in packages:
        lines.append(f"{name}=={version} \\")
        for index, value in enumerate(hashes):
            suffix = " \\" if index < len(hashes) - 1 else ""
            lines.append(f"    --hash=sha256:{value}{suffix}")
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
