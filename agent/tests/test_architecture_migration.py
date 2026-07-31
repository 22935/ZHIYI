"""AgentOS 迁移后目录边界、Pack 位置和兼容入口存在性的架构测试。"""


from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_agentos_core_imports_from_runtime_package():
    import agentos
    from agentos.core.runtime import build_default_runtime

    package_path = Path(agentos.__file__).resolve()

    assert package_path.is_relative_to(PROJECT_ROOT / "agentOS" / "src")
    assert callable(build_default_runtime)


def test_core_runtime_is_split_into_workflow_models_and_governance_layers():
    core_dir = PROJECT_ROOT / "agentOS" / "src" / "agentos" / "core"

    assert (core_dir / "runtime.py").is_file()
    for layer in ("models", "workflow", "governance"):
        assert (core_dir / layer / "__init__.py").is_file()

    assert not (core_dir / "workflow_runtime.py").exists()
    assert not (core_dir / "workflow_registry.py").exists()
    assert not (core_dir / "types.py").exists()
    assert not (core_dir / "registry.py").exists()
    assert not (core_dir / "orchestrator.py").exists()
    assert not (core_dir / "state_machine.py").exists()
    assert not (core_dir / "task_manager.py").exists()
    assert not (core_dir / "trace.py").exists()
    assert not (core_dir / "checkpoint.py").exists()
    assert not (core_dir / "review.py").exists()
    assert not (core_dir / "evaluation.py").exists()
    assert not (core_dir / "planner.py").exists()
    assert not (core_dir / "scheduler.py").exists()

    from agentos.core.models.types import WorkflowDefinition
    from agentos.core.workflow.registry import WorkflowRegistry
    from agentos.core.governance.trace import TraceStore

    assert WorkflowDefinition.__name__ == "WorkflowDefinition"
    assert WorkflowRegistry.__name__ == "WorkflowRegistry"
    assert TraceStore.__name__ == "TraceStore"


def test_core_agents_do_not_contain_domain_implementations():
    core_agents_dir = PROJECT_ROOT / "agentOS" / "src" / "agentos" / "agents"

    assert not (core_agents_dir / "legal").exists()
    assert not (core_agents_dir / "education").exists()


def test_pack_registry_discovers_application_layer_packs():
    from agentos.packs.registry import discover_pack_manifests

    manifests = discover_pack_manifests()
    by_id = {manifest.pack_id: manifest for manifest in manifests}

    assert {"kinlin.legal", "education", "programmer", "writer"}.issubset(by_id)
    assert by_id["kinlin.legal"].module == "packs.legal"
    assert by_id["kinlin.legal"].path.is_relative_to(PROJECT_ROOT / "agent" / "packs")


def test_core_packs_directory_only_contains_registry_code():
    core_packs_dir = PROJECT_ROOT / "agentOS" / "src" / "agentos" / "packs"

    for pack_id in ("legal", "education", "programmer", "writer"):
        assert not (core_packs_dir / pack_id).exists()


def test_domain_skills_live_in_application_layer_packs():
    core_skills_dir = PROJECT_ROOT / "agentOS" / "src" / "agentos" / "skills"
    app_packs_dir = PROJECT_ROOT / "agent" / "packs"

    assert not (core_skills_dir / "builtin").exists()
    for pack_id in ("legal", "education", "programmer", "writer"):
        assert (app_packs_dir / pack_id / "skills").is_dir()


def test_pack_path_resolves_application_layer_pack_resources():
    from agentos.packs.registry import default_packs_dir, pack_path

    assert default_packs_dir() == PROJECT_ROOT / "agent" / "packs"
    assert pack_path("education", "data", "knowledge_points.json") == (
        PROJECT_ROOT / "agent" / "packs" / "education" / "data" / "knowledge_points.json"
    )


def test_core_agent_and_skill_interfaces_use_single_canonical_file_names():
    core_dir = PROJECT_ROOT / "agentOS" / "src" / "agentos"

    assert (core_dir / "agents" / "base.py").is_file()
    assert (core_dir / "agents" / "registry.py").is_file()
    assert (core_dir / "skills" / "base.py").is_file()
    assert not (core_dir / "agents" / "base_agent.py").exists()
    assert not (core_dir / "agents" / "agent_registry.py").exists()
    assert not (core_dir / "skills" / "base_skill.py").exists()
