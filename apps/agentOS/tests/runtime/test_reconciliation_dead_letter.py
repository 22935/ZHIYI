"""身份 outbox 消费轮的死信旁路语义。"""

from __future__ import annotations

from runtime.reconciliation import (
    DEAD_LETTER_MAX_ATTEMPTS,
    IdentityProjectionReconciler,
    IdentityReconciliationReport,
)


class _StaticOutboxStore:
    def __init__(self, events: list[dict]) -> None:
        self.events = events
        self.marks: list[tuple[str, bool]] = []

    def list_outbox(self, *, limit: int = 200) -> list[dict]:
        return list(self.events)[:max(1, limit)]

    def mark_outbox(self, event_id: str, *, applied: bool, error: str | None = None) -> None:
        self.marks.append((event_id, applied))


def test_poisoned_outbox_event_is_bypassed_after_delivery_cap() -> None:
    """投递次数达到上限的毒事件被旁路：不再触达投影，也不计入 failures。

    2026-09-10 事故中，一条死信在崩溃循环里被无条件重试了上百次；旁路后
    它留在 outbox 等待人工修复，不再拖垮无关 Run 的 flush。
    """
    store = _StaticOutboxStore([
        {
            "event_id": "attempt.ensured:attempt_dead",
            "event_type": "attempt.ensured",
            "aggregate_id": "run_b1bf757c84b2",
            "payload": "{}",
            "attempts": DEAD_LETTER_MAX_ATTEMPTS,
        },
    ])

    def _explode(*args, **kwargs):
        raise AssertionError("dead-letter bypass must not touch the projection")

    adapter = type("Adapter", (), {
        "repositories": type("Repositories", (), {
            "inbox_events": type("Inbox", (), {
                "begin": staticmethod(_explode),
                "mark_failed": staticmethod(_explode),
            }),
        })(),
    })()
    report = IdentityReconciliationReport()

    IdentityProjectionReconciler(adapter)._consume_execution_outbox(store, report, limit=10)

    assert report.dead_letter_count == 1
    assert report.failures == []
    assert report.failed_aggregate_ids == set()
    assert store.marks == []


def test_fresh_outbox_event_is_still_consumed_below_the_cap() -> None:
    """低于上限的失败事件仍走正常消费路径（标记 failed 并计入 failures）。"""
    store = _StaticOutboxStore([
        {
            "event_id": "attempt.ensured:attempt_fresh",
            "event_type": "attempt.ensured",
            "aggregate_id": "run_x",
            "payload": "{}",
            "attempts": DEAD_LETTER_MAX_ATTEMPTS - 1,
        },
    ])

    class _FailingInbox:
        @staticmethod
        def begin(event):
            raise RuntimeError("projection rejected the event")

        @staticmethod
        def mark_failed(event_id, error):
            store.marks.append((event_id, False))

    adapter = type("Adapter", (), {
        "repositories": type("Repositories", (), {"inbox_events": _FailingInbox})(),
    })()
    report = IdentityReconciliationReport()

    IdentityProjectionReconciler(adapter)._consume_execution_outbox(store, report, limit=10)

    assert report.dead_letter_count == 0
    assert len(report.failures) == 1
    assert "attempt_fresh" in report.failures[0]
    assert store.marks == [("attempt.ensured:attempt_fresh", False)]
