"""低熵通信子系统契约测试。

锁定不变量：按 input_spec 精准投递（不全盘倾倒）、证据链聚合、Token 节省率
计算、数据血缘双向追溯。
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from agentos.core.acg import ACGBlueprint, ACGEdge, EdgeType, StepNode
from agentos.core.communication import (
    ContextAssembler,
    ProvenanceLedger,
    estimate_tokens,
)


def _two_step_graph(input_spec: dict) -> tuple[ACGBlueprint, StepNode]:
    bp = ACGBlueprint(objective="comm-test")
    up = StepNode(nodeId="up", name="up", agentName="x")
    down = StepNode(nodeId="down", name="down", agentName="y", inputSpec=input_spec)
    bp.nodes += [up, down]
    bp.edges.append(ACGEdge(sourceId="up", targetId="down", edgeType=EdgeType.DEPENDENCY))
    return bp, down


def test_estimate_tokens_monotonic():
    assert estimate_tokens("") == 0
    assert estimate_tokens(None) == 0
    short = estimate_tokens({"a": "x" * 10})
    long = estimate_tokens({"a": "x" * 1000})
    assert long > short


def test_assembler_precise_delivery_by_fields():
    bp, down = _two_step_graph({"fields": ["summary", "risk_count"]})
    asm = ContextAssembler()
    upstream = {
        "up": {
            "summary": "短摘要",
            "risk_count": 3,
            "full_text": "x" * 5000,
            "raw_dump": "y" * 5000,
        }
    }
    asm.record_production("up", upstream["up"])
    pack = asm.assemble(
        run_id="r1", blueprint=bp, step_node=down, objective="demo", upstream_outputs=upstream
    )
    # 只投递清单字段，不倾倒 full_text/raw_dump
    assert sorted(pack.data.keys()) == ["risk_count", "summary"]
    assert "full_text" not in pack.data
    assert pack.saving_ratio > 0.9
    assert pack.tokens_delivered < pack.tokens_available
    assert pack.source_data == {"up": {"summary": "短摘要", "risk_count": 3}}


def test_assembler_directed_from_map():
    bp = ACGBlueprint(objective="from-map")
    a = StepNode(nodeId="a", name="a", agentName="x")
    b = StepNode(nodeId="b", name="b", agentName="x")
    c = StepNode(nodeId="c", name="c", agentName="y", inputSpec={"from": {"a": ["alpha"], "b": ["beta"]}})
    bp.nodes += [a, b, c]
    bp.edges += [
        ACGEdge(sourceId="a", targetId="c", edgeType=EdgeType.DEPENDENCY),
        ACGEdge(sourceId="b", targetId="c", edgeType=EdgeType.DEPENDENCY),
    ]
    asm = ContextAssembler()
    upstream = {"a": {"alpha": 1, "noise": "z" * 999}, "b": {"beta": 2, "noise": "z" * 999}}
    pack = asm.assemble(run_id="r", blueprint=bp, step_node=c, objective="o", upstream_outputs=upstream)
    assert pack.data == {"alpha": 1, "beta": 2}
    assert set(pack.source_step_ids) == {"a", "b"}


def test_assembler_aggregates_evidence_chain():
    bp, down = _two_step_graph({"fields": ["summary"]})
    asm = ContextAssembler()
    upstream = {"up": {"summary": "s", "evidence_refs": ["ev1", "ev2"]}}
    pack = asm.assemble(run_id="r", blueprint=bp, step_node=down, objective="o", upstream_outputs=upstream)
    assert pack.evidence_refs == ["ev1", "ev2"]


def test_assembler_fallback_passthrough_without_spec():
    bp, down = _two_step_graph({})  # 无清单 → 回退透传，但仍记账
    asm = ContextAssembler()
    upstream = {"up": {"a": 1, "b": 2}}
    pack = asm.assemble(run_id="r", blueprint=bp, step_node=down, objective="o", upstream_outputs=upstream)
    assert pack.data == {"a": 1, "b": 2}
    # 透传时节省率为 0（投递=可获取）
    assert pack.saving_ratio == 0.0


def test_provenance_bidirectional_trace():
    ledger = ProvenanceLedger()
    ledger.record_production("a", {"x": 1}, 10)
    ledger.record_production("b", {"y": 2}, 10)
    ledger.record_consumption("b", ["a"], ["x"])
    ledger.record_consumption("c", ["b"], ["y"])
    # 前向追溯 c：消费链应回溯到 a
    assert ledger.trace_backward("c") == ["a", "b"]
    # 后向影响 a：影响到 b（再到 c 是间接，trace_forward 只看直接消费者）
    assert ledger.trace_forward("a") == ["b"]
    graph = ledger.to_graph()
    assert len(graph["productions"]) == 2
    assert len(graph["consumptions"]) == 2


def test_provenance_v2_interaction_hash_chain_roundtrip():
    ledger = ProvenanceLedger(run_id="run-1", task_id="task-1")
    ledger.record_production("a", {"wanted": 1, "secret": 2}, 10, agent_name="producer")
    ledger.record_consumption(
        "b",
        ["a"],
        ["wanted"],
        consumer_agent_name="consumer",
        fields_by_producer={"a": ["wanted"]},
        data={"wanted": 1},
        tokens_delivered=2,
        tokens_available=10,
        saving_ratio=0.8,
    )
    ledger.record_interaction(
        edge_ids=["edge-1"],
        producer_step_ids=["a"],
        consumer_step_id="b",
        producer_agent_names=["producer"],
        consumer_agent_name="consumer",
        fields_by_producer={"a": ["wanted"]},
        tokens_delivered=2,
        tokens_available=10,
        saving_ratio=0.8,
        evidence_refs=[],
        contract_status="valid",
        data={"wanted": 1},
    )

    graph = ledger.to_graph()
    assert graph["schemaVersion"] == 2
    assert graph["integrityStatus"] == "valid"
    assert len(graph["interactions"]) == 1
    restored = ProvenanceLedger.from_graph(graph, run_id="run-1", task_id="task-1")
    assert restored.verify_integrity()
