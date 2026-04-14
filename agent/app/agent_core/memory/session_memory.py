from threading import Lock
from typing import Dict, List


class SessionMemoryStore:
    """Simple in-memory session memory store."""

    def __init__(self, max_messages_per_session: int = 20):
        self._max_messages = max_messages_per_session
        self._store: Dict[str, List[Dict[str, str]]] = {}
        self._lock = Lock()

    def get_history(self, session_id: str) -> List[Dict[str, str]]:
        with self._lock:
            return list(self._store.get(session_id, []))

    def append_message(self, session_id: str, role: str, content: str) -> None:
        with self._lock:
            history = self._store.setdefault(session_id, [])
            history.append({"role": role, "content": content})
            if len(history) > self._max_messages:
                self._store[session_id] = history[-self._max_messages :]

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._store.pop(session_id, None)


session_memory_store = SessionMemoryStore()

