"""Compatibility module for lowercase ``agentos`` imports.

The application layer can be launched with ``agent/`` as the first import
root. In that mode this module is discovered before the real package under
``agentOS/src``. Expose the real package path so existing ``import agentos``
callers continue to resolve AgentOS Core from the runtime package.
"""

from pathlib import Path

_module_path = Path(__file__).resolve()
_docker_package_path = _module_path.parent / "agentOS" / "src" / "agentos"
_repo_package_path = _module_path.parents[1] / "agentOS" / "src" / "agentos"

__path__ = [str(_docker_package_path if _docker_package_path.exists() else _repo_package_path)]
