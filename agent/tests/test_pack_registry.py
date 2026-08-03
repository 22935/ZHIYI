"""应用层 Pack 发现、注册和最小工作流执行路径的回归测试。"""


import asyncio

from agentos.agents import AgentRegistry
from agentos.core.runtime import WorkflowRuntime
from agentos.core.planning.default_catalog import build_default_capability_catalog
from agentos.core.workflow.registry import WorkflowRegistry
from agentos.core.models.types import WorkflowStatus
from agentos.packs.registry import discover_pack_manifests, register_installed_packs
from app.api.agentos_core import LEGACY_AGENT_CONFIG


def test_pack_registry_discovers_installed_manifests():
    manifests = discover_pack_manifests()

    assert {manifest.pack_id for manifest in manifests} >= {
        "education",
        "kinlin.legal",
        "programmer",
        "writer",
    }
    assert next(
        manifest for manifest in manifests if manifest.pack_id == "kinlin.legal"
    ).module == "packs.legal"
    assert set(
        next(
            manifest
            for manifest in manifests
            if manifest.pack_id == "kinlin.legal"
        ).capabilities
    ) == {
        "文本解析",
        "条款分类",
        "风险识别",
        "证据检索",
        "修改建议",
        "人工审核",
        "报告生成",
    }


def test_each_professional_role_is_bound_to_a_declared_pack_workflow():
    manifests = {manifest.pack_id: manifest for manifest in discover_pack_manifests()}

    for role, config in LEGACY_AGENT_CONFIG.items():
        plugin_id = config["plugin_id"]
        workflow_id = config["workflow_id"]
        assert plugin_id in manifests, role
        assert workflow_id in manifests[plugin_id].workflows, role


def test_pack_registry_registers_enabled_packs_from_manifest():
    agent_registry = AgentRegistry()
    workflow_registry = WorkflowRegistry()
    capability_catalog = build_default_capability_catalog()

    registered = register_installed_packs(
        agent_registry=agent_registry,
        workflow_registry=workflow_registry,
        capability_catalog=capability_catalog,
    )

    assert "kinlin.legal" in {manifest.pack_id for manifest in registered}
    assert workflow_registry.get("legal_case_analysis_v1").domain == "legal"
    assert agent_registry.resolve("legal", agent_name="case_intake").profile.agent_name == "case_intake"
    assert capability_catalog.resolve("法律知识应用").capability_id == "证据检索"


def test_non_legal_packs_register_minimal_workflows():
    asyncio.run(_test_non_legal_packs_register_minimal_workflows())


async def _test_non_legal_packs_register_minimal_workflows():
    agent_registry = AgentRegistry()
    workflow_registry = WorkflowRegistry()
    capability_catalog = build_default_capability_catalog()
    register_installed_packs(
        agent_registry=agent_registry,
        workflow_registry=workflow_registry,
        capability_catalog=capability_catalog,
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
