"""记忆器细节逻辑的回归测试：工作记忆方法与存储并发基线。"""

from __future__ import annotations

import threading

from components.memory.models import PhaseCapsule, WorkingMemory
from components.memory.service import MemoryService
from components.memory.store import SQLiteMemoryStore
from contracts.memory import MemoryRecord, MemoryType


def test_working_memory_owns_record_and_context_pack_projection() -> None:
    run = {"runId": "run-1", "input": {"topic": "lease"}}
    pack = {"sourceData": {"step-a": {"summary": "done"}, "step-b": "not-a-mapping"}}

    memory = WorkingMemory.from_context_pack(run, pack)

    assert memory.run_id == "run-1"
    assert memory.task_input == {"topic": "lease"}
    assert memory.observations == {"step-a": {"summary": "done"}}

    memory.record("step-c", {"summary": "recorded"})
    assert memory.observations["step-c"] == {"summary": "recorded"}

    # 冻结的胶囊模型不应再持有工作记忆的方法，避免误调用后抛 AttributeError。
    assert not hasattr(PhaseCapsule, "record")
    assert not hasattr(PhaseCapsule, "from_context_pack")


def test_phase_capsule_reports_risk_for_tagless_source_record() -> None:
    service = MemoryService()
    service.remember(
        MemoryRecord(
            memoryId="memory:run-1:reviewed",
            memoryType=MemoryType.SEMANTIC,
            content={"decision": "review", "summary": "pending evidence"},
            scope="run-1",
        )
    )

    capsule = service.create_phase_capsule(
        run_id="run-1",
        phase_id="phase-1",
        source_memory_refs=["memory:run-1:reviewed"],
    )

    assert capsule.risks == ["semantic:review"]
    assert capsule.decisions == ["review"]


def test_sqlite_store_uses_wal_and_accepts_cross_thread_writes(tmp_path) -> None:
    store = SQLiteMemoryStore(db_path=tmp_path / "memory.sqlite3")
    try:
        assert store._connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert store._connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000

        failures: list[BaseException] = []

        def write_from_worker(worker_id: int) -> None:
            try:
                store.put(
                    MemoryRecord(
                        memoryId=f"memory:run-1:worker-{worker_id}",
                        memoryType=MemoryType.WORKING,
                        content={"worker": worker_id},
                        scope="run-1",
                    )
                )
            except BaseException as exc:  # pragma: no cover - 失败时用于报错定位
                failures.append(exc)

        workers = [threading.Thread(target=write_from_worker, args=(index,)) for index in range(4)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()

        assert failures == []
        assert {record.memory_id for record in store.values()} == {
            f"memory:run-1:worker-{index}" for index in range(4)
        }
    finally:
        store.close()
