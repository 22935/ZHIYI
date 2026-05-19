import asyncio

from agentos.agents import AgentRegistry
from agentos.core.workflow_runtime import WorkflowRuntime
from agentos.core.workflow_registry import WorkflowRegistry
from agentos.core.types import WorkflowStatus
from agentos.packs.registry import discover_pack_manifests, register_installed_packs


def test_pack_registry_discovers_installed_manifests():
    manifests = discover_pack_manifests()

    assert {manifest.pack_id for manifest in manifests} >= {
        "education",
        "legal",
        "programmer",
        "writer",
    }
    assert next(manifest for manifest in manifests if manifest.pack_id == "legal").module == "agentos.packs.legal"


def test_pack_registry_registers_enabled_packs_from_manifest():
    agent_registry = AgentRegistry()
    workflow_registry = WorkflowRegistry()

    registered = register_installed_packs(
        agent_registry=agent_registry,
        workflow_registry=workflow_registry,
    )

    assert "legal" in {manifest.pack_id for manifest in registered}
    assert workflow_registry.get("legal_case_analysis_v1").domain == "legal"
    assert agent_registry.resolve("legal", agent_name="case_intake").profile.agent_name == "case_intake"


def test_non_legal_packs_register_minimal_workflows():
    asyncio.run(_test_non_legal_packs_register_minimal_workflows())


async def _test_non_legal_packs_register_minimal_workflows():
    agent_registry = AgentRegistry()
    workflow_registry = WorkflowRegistry()
    register_installed_packs(
        agent_registry=agent_registry,
        workflow_registry=workflow_registry,
    )
    runtime = WorkflowRuntime(agent_registry=agent_registry, workflow_registry=workflow_registry)

    cases = [
        (
            "education",
            "lesson_plan",
            "education_lesson_plan_v1",
            "lesson_plan",
            {"topic": "勾股定理", "grade": "八年级", "subject": "数学"},
        ),
        (
            "programmer",
            "requirement_analysis",
            "programmer_requirement_analysis_v1",
            "requirement_analysis",
            {"requirement": "实现用户登录接口", "targetLanguage": "python"},
        ),
        (
            "writer",
            "story_outline",
            "writer_story_outline_v1",
            "outline_generate",
            {"premise": "时间旅行者修复城市记忆", "genre": "科幻"},
        ),
    ]

    for domain, intent, workflow_id, agent_name, task_input in cases:
        task = runtime.create_task(
            title=f"{domain} smoke task",
            domain=domain,
            intent=intent,
            input=task_input,
        )
        assert task.recommended_workflow == workflow_id
        assert agent_registry.resolve(domain, agent_name=agent_name).profile.domain == domain

        run = await runtime.start(task.task_id)

        assert run.status == WorkflowStatus.COMPLETED
        assert run.workflow_id == workflow_id
        assert run.output["final_answer"]
        if domain == "writer":
            assert "小说大纲" in run.output["final_answer"]
            assert "Story outline ready" not in run.output["final_answer"]
