import asyncio

from agentos.agents import AgentRegistry
from agentos.core.types import ReviewDecision, ReviewDecisionType, StepStatus, WorkflowStatus
from agentos.core.runtime import WorkflowRuntime
from agentos.core.workflow.registry import WorkflowRegistry
from packs.legal import register_pack as register_legal_pack


def test_langgraph_contract_review_migrates_to_agentos_workflow():
    asyncio.run(_test_langgraph_contract_review_migrates_to_agentos_workflow())


async def _test_langgraph_contract_review_migrates_to_agentos_workflow():
    agent_registry = AgentRegistry()
    workflow_registry = WorkflowRegistry()
    register_legal_pack(agent_registry=agent_registry, workflow_registry=workflow_registry)
    runtime = WorkflowRuntime(agent_registry=agent_registry, workflow_registry=workflow_registry)

    workflow = workflow_registry.get("legal_contract_review_langgraph_v1")
    assert [step.step_id for step in workflow.steps] == [
        "contract_parse",
        "clause_classify",
        "risk_detect",
        "legal_evidence_match",
        "revision_suggest",
        "human_review",
        "report_generate",
        "final_review",
    ]

    task = runtime.create_task(
        title="软件开发服务合同审查",
        domain="legal",
        intent="contract_review_langgraph",
        input={
            "source": "workbench",
            "contractText": "甲方委托乙方开发 CRM 系统，合同约定签署后支付 30%，系统上线后支付 70%，"
            "如无重大问题视为验收通过，项目源代码归双方共同所有。",
        },
    )

    run = await runtime.start(
        task_id=task.task_id,
        workflow_id="legal_contract_review_langgraph_v1",
        review_mode="human_in_loop",
    )

    assert run.status == WorkflowStatus.WAITING_REVIEW
    assert run.current_step_id == "human_review"
    assert run.get_step("contract_parse").output["contract_type"] == "软件开发服务合同"
    assert run.get_step("clause_classify").output["clause_count"] == 7
    assert len(run.get_step("risk_detect").output["risks"]) == 3
    assert len(run.get_step("legal_evidence_match").output["evidences"]) == 4
    assert len(run.get_step("revision_suggest").output["revision_suggestions"]) == 3
    assert run.get_step("human_review").status == StepStatus.WAITING_REVIEW
    assert run.get_step("report_generate").status == StepStatus.PENDING

    completed = await runtime.apply_review(
        ReviewDecision(
            runId=run.run_id,
            stepId="human_review",
            decision=ReviewDecisionType.APPROVED,
            reviewer="legal_reviewer",
            comment="风险结论可进入报告生成。",
        )
    )

    assert completed.status == WorkflowStatus.COMPLETED
    artifacts = completed.output["artifacts"]
    assert "软件开发服务合同审查报告" in artifacts["report_generate"]["report_markdown"]
    assert artifacts["report_generate"]["report"]["reviewStatus"] == "approved"
    assert "已完成合同审查迁移工作流" in completed.output["final_answer"]
    assert "LangGraph 节点语义已迁移到 AgentOS WorkflowRun" in artifacts["final_review"]["review_notes"]
    assert completed.get_step("report_generate").status == StepStatus.COMPLETED
    assert completed.get_step("final_review").status == StepStatus.COMPLETED
