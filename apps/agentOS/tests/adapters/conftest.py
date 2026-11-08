"""Make the agent workspace importable for cross-boundary adapter tests.

Some adapter integration tests (e.g. test_hands_integration) exercise the
agent-side workspace tools (`app.*`, `packs.*`) that live under apps/agent.
agentOS's own pytest pythonpath only exposes agentOS/src, so add apps/agent
here — scoped to this directory only — without changing the global root.
"""

import sys
from pathlib import Path

_AGENT_ROOT = Path(__file__).resolve().parents[3] / "agent"
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))
