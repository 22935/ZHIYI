from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def test_real_terminal_edge_cloud_process_demo(tmp_path: Path) -> None:
    runner = Path(__file__).resolve().parents[3] / "tools" / "edge_cloud_demo" / "run_demo.py"
    result = subprocess.run(
        [sys.executable, str(runner), "--work-dir", str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    report = json.loads(result.stdout)
    assert report["registration"]["edge"]["resourceId"] == "edge-01"
    assert report["execution"]["initial"]["signatureVerified"] is True
    assert report["execution"]["afterEdgeFailure"]["selectedResourceId"] == "cloud-01"
    assert report["execution"]["afterEdgeFailure"]["failoverApplied"] is True
    assert report["execution"]["afterEdgeTermination"]["selectedResourceId"] == "cloud-01"
    assert report["recovery"]["edgeHealthyAfterRestart"] is True
    assert report["recovery"]["healthSource"] == "SQLiteResourceHealthStore"
