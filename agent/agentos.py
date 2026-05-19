"""Compatibility module for lowercase ``agentos`` imports on Linux."""

from pathlib import Path

__path__ = [str(Path(__file__).resolve().parent / "agentOS")]
