"""Architecture gates for the AgentOS competition capability upgrade."""

from __future__ import annotations

import ast
import re
from pathlib import Path
import pytest

from components.executor.graph import ACGExecutionGraph
from runtime.workflow_runtime import ExecutionRuntime


SRC = Path(__file__).resolve().parents[2] / "src"


def _python_sources(root: Path):
    yield from sorted(root.rglob("*.py"))


def _defined_classes(root: Path) -> set[str]:
    names: set[str] = set()
    for path in _python_sources(root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        names.update(node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef))
    return names


def test_workflow_runtime_and_acg_graph_remain_the_only_execution_truth() -> None:
    """Capability work must not introduce a parallel DAG runtime/state machine."""
    assert ExecutionRuntime.__module__ == "runtime.workflow_runtime"
    assert ACGExecutionGraph.__module__ == "components.executor.graph"
    forbidden = {"RuntimeGraph", "SchedulerGraph", "EvolutionRuntime", "LongTermMemoryRuntime"}
    assert _defined_classes(SRC).isdisjoint(forbidden)


def test_scheduler_has_no_dag_readiness_dependency() -> None:
    """Scheduler may consume READY work but must not import or construct the DAG."""
    scheduler_root = SRC / "components" / "scheduler"
    forbidden_modules = {"components.executor.graph", "components.executor.state_graph"}
    for path in _python_sources(scheduler_root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        )
        assert imports.isdisjoint(forbidden_modules), path


def test_resource_plane_is_the_only_resource_state_authority() -> None:
    """资源平面只有一个状态权威；目录/独立注册表门面已随重构删除。"""
    resource_root = SRC / "components" / "resource"
    remaining = {path.name for path in resource_root.glob("*.py")}
    assert remaining.isdisjoint({
        "directory.py", "agent_directory.py", "agent_service.py",
        "agent_store.py", "node_service.py", "registry.py",
    })
    from components.resource.service import ResourcePlane

    plane = ResourcePlane()
    # Node/Runtime/ModelEndpoint 状态都收敛在同一服务实例里。
    assert hasattr(plane, "register_runtime") and hasattr(plane, "register_node")
    assert hasattr(plane, "upsert_model_endpoint") and hasattr(plane, "runtime_candidates")


def test_local_runtime_is_only_a_contract_and_transport_boundary() -> None:
    """Host tools must not create a parallel authority or execute inside AgentOS."""
    local_files = (SRC / "contracts" / "local_runtime.py", SRC / "adapters" / "local_runtime.py")
    forbidden_classes = {"CapabilityRegistry", "ResourceRegistry", "RuntimeEventBroker"}
    forbidden_imports = {
        "service.agents.base", "app.tools.terminal", "app.tools.chat_catalog",
        "subprocess", "httpx", "requests", "socket",
    }
    forbidden_calls = {"exec", "eval", "system", "Popen", "run", "create_subprocess_shell"}
    for path in local_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        classes = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
        imports = {
            alias.name
            for node in ast.walk(tree) if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        )
        calls = {
            node.func.id for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert classes.isdisjoint(forbidden_classes), path
        assert imports.isdisjoint(forbidden_imports), path
        assert calls.isdisjoint(forbidden_calls), path


def test_local_runtime_http_transport_keeps_the_low_level_boundary() -> None:
    """HTTP Local Runtime transport must not become the AgentRun adapter."""
    path = SRC / "adapters" / "local_runtime_http.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert "AgentRunContext" not in names
    assert "AgentOutput" not in names
    assert "HttpResourceExecutionAdapter" not in names
    assert "LocalRuntimeExecutionRequest" in names
    assert "LocalRuntimeExecutionResult" in names
    assert "AgentRunContext" not in attributes


def test_native_process_execution_stays_in_the_hands_backend() -> None:
    """原生进程宿主的唯一归属是 Hands；它不内嵌 AgentOS 权威，Python 侧不得复活 Local Runtime。

    ``225d1934`` 退役了 ``apps/local-runtime``（Python 执行宿主），执行改由
    ``apps/agentOS/src/hands``（TS，逐字复用 DSH 执行基座）承载。门禁随主体迁移，
    但两条纪律不变：① 退役的 Python 宿主不能悄悄回来；② 原生执行只能待在 Hands 树内。
    """
    apps = SRC.parents[1]
    assert not (apps / "local-runtime").exists(), "Local Runtime 已退役：原生执行宿主只允许 Hands"

    hands_root = SRC / "hands"
    supervisor_sources = [
        path for path in hands_root.rglob("*.ts")
        if "node_modules" not in path.parts and "windows-job" in path.name
    ]
    assert supervisor_sources, "Hands 必须继续承载 Windows Job-Object 执行守卫"
    for path in supervisor_sources:
        source = path.read_text(encoding="utf-8")
        for authority in ("CapabilityRegistry", "ResourceRegistry", "RuntimeEventBroker"):
            assert authority not in source, f"{path} 内嵌了 AgentOS 权威 {authority}"

    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        )
        assert "local_runtime.process" not in imported, path
        assert "local_runtime.security" not in imported, path


def test_agentos_does_not_host_native_process_execution() -> None:
    """Native subprocess and Windows Job Object code stay in the Hands backend."""
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        )
        assert "subprocess" not in imports, path
        assert "ProcessExecutionService" not in path.read_text(encoding="utf-8"), path


def test_windows_isolation_stays_inside_the_hands_backend() -> None:
    """OS identity, ACL, and Job Object code cannot cross into AgentOS.

    Local Runtime（Python 宿主）退役后，Windows 隔离实现随执行基座一起落在
    ``apps/agentOS/src/hands``（受限令牌 + ACL + Job Object，逐字复用 DSH）。
    审计边界不变：这些原语绝不能出现在 AgentOS 的 Python 源码里。
    """
    agentos_source = "\n".join(
        path.read_text(encoding="utf-8") for path in SRC.rglob("*.py")
    )
    assert "WindowsWorkspaceSecurityLease" not in agentos_source
    assert "CreateAppContainerToken" not in agentos_source
    assert "CreateRestrictedToken" not in agentos_source
    assert "CreateJobObjectW" not in agentos_source

    hands_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (SRC / "hands").rglob("*.ts")
        if "node_modules" not in path.parts
    )
    assert "SetNamedSecurityInfoW" in hands_source, "ACL 隔离实现必须留在 Hands 执行基座内"
    assert "CreateRestrictedToken" in hands_source, "受限令牌实现必须留在 Hands 执行基座内"
    assert "CreateJobObject" in hands_source, "Job Object 实现必须留在 Hands 执行基座内"


def test_acg_does_not_expose_shell_execution_in_pr6() -> None:
    """PR-6 supplies the host primitive only; ACG remains unchanged."""
    acg_root = SRC / "components" / "executor"
    source = "\n".join(path.read_text(encoding="utf-8") for path in _python_sources(acg_root))
    assert "shell.exec" not in source
    assert "ProcessExecutionService" not in source


def test_local_runtime_integration_does_not_route_chat_acg_or_desktop_host() -> None:
    """Chat may use the AgentOS Local Runtime seam without creating a parallel authority."""
    chat_api = SRC.parents[1] / "agent" / "app" / "api" / "chat.py"
    chat_catalog = SRC.parents[1] / "agent" / "app" / "tools" / "chat_catalog.py"
    chat_executor = SRC.parents[1] / "agent" / "app" / "tools" / "local_runtime.py"
    assert "get_chat_tool_runtime" in chat_api.read_text(encoding="utf-8")
    assert "ResourceService(" not in chat_api.read_text(encoding="utf-8")
    assert "FilesystemCapabilities" not in chat_catalog.read_text(encoding="utf-8")
    assert "LocalRuntimeExecutor" not in chat_catalog.read_text(encoding="utf-8")
    assert "LocalRuntimeToolExecutor" in chat_catalog.read_text(encoding="utf-8")
    catalog_source = chat_catalog.read_text(encoding="utf-8")
    assert "run_command" in catalog_source
    assert "ProcessExecutionService" not in catalog_source
    assert "subprocess" not in catalog_source
    assert "AgentRunContext" not in chat_executor.read_text(encoding="utf-8")



def _assert_desktop_execution_boundary(sources: dict[str, str]) -> None:
    """IDE helpers may spawn fixed tools; none may become a Run executor."""
    reviewed_ide_hosts = {
        'lib/lsp-client.ts': ('spawn(this.options.command, this.options.args', 'this.child?.kill()'),
        'lib/workspace-git.ts': ("spawn('git', args", 'GIT_TIMEOUT_MS', 'MAX_OUTPUT_BYTES', 'child.kill()'),
        'lib/workspace-search.ts': ("spawn('rg', args", 'RIPGREP_TIMEOUT_MS', 'child.kill()'),
        'lib/workspace-diagnostics.ts': ('runProcess(process.execPath', "'typescript', 'bin', 'tsc'",
            "['-m', 'ruff', '--version']", 'TSC_TIMEOUT_MS', 'RUFF_TIMEOUT_MS', 'child.kill()'),
    }
    process_hosts = set()
    for name, source in sources.items():
        for marker in ('LocalRuntime', 'ExecutionBackend', 'WorkflowStore', 'ExecutionRuntime', 'NodeRunner', 'ACGExecutionGraph'):
            assert marker not in source, f'{name} embeds {marker}'
        if 'child_process' not in source:
            continue
        process_hosts.add(name)
        assert name in reviewed_ide_hosts, f'{name} is an unreviewed process host'
        imports = re.findall(r"import\s*\{([^}]+)\}\s*from\s*['\"]node:child_process['\"]", source)
        assert len(imports) == 1, f'{name} must use the reviewed named spawn import'
        assert set(item.strip() for item in imports[0].split(',')) <= {'spawn', 'type ChildProcessWithoutNullStreams'}
        assert not re.search(r'\bshell\s*:\s*true', source), f'{name} enables shell execution'
        for marker in ('missionId', 'runId', 'runtimeRevision', 'operationId', 'executionPermit'):
            assert marker not in source, f'{name} accepts Run execution identity {marker}'
        assert all(fragment in source for fragment in reviewed_ide_hosts[name]), f'{name} changed its bounded IDE invocation'
    assert process_hosts == set(reviewed_ide_hosts)
    assert not re.search(r'export\s+(?:async\s+)?(?:function|const)\s+runProcess', sources['lib/workspace-diagnostics.ts'])
    assert not re.search(r'export\s+(?:async\s+)?(?:function|const)\s+runGit', sources['lib/workspace-git.ts'])
    assert 'command: process.execPath' in sources['lib/lsp-host.ts']
    assert "args: [this.serverPath, '--stdio']" in sources['lib/lsp-host.ts']
    main = sources['main.ts']
    channels = {'lspOpen', 'lspChange', 'lspClose', 'lspDiagnostics', 'lspDefinition', 'workspaceSearch',
        'workspaceDiagnostics', 'workspaceGitStatus', 'workspaceGitDiff', 'workspaceGitShow',
        'workspaceGitStage', 'workspaceGitUnstage', 'workspaceGitCommit', 'workspaceGitInit'}
    handlers = list(re.finditer(r'ipcMain.handle\(IPC\.(lsp\w+|workspace(?:Search|Diagnostics|Git\w+)),\s*async\s*\([^)]*\)\s*=>\s*\{\s*guard\(event\)', main))
    assert {match[1] for match in handlers} == channels, 'IDE IPC lost its owner renderer guard'
    for match in handlers:
        end = main.find('ipcMain.handle(', match.end())
        body = main[match.end():end if end >= 0 else len(main)]
        validator = 'validateGitRoot' if match[1].startswith('workspaceGit') else 'validateSearchRoot' if match[1] == 'workspaceSearch' else 'validateDiagnosticsRoot'
        assert f'await {validator}(root)' in body, f'{match[1]} lost its workspace root boundary'


def _desktop_sources() -> dict[str, str]:
    electron_src = SRC.parents[1] / "desktop" / "electron" / "src"
    assert electron_src.is_dir(), "Electron host sources are expected under apps/desktop/electron/src"
    return {path.relative_to(electron_src).as_posix(): path.read_text(encoding='utf-8') for path in electron_src.rglob('*.ts')}


def test_electron_host_does_not_embed_execution_authority() -> None:
    _assert_desktop_execution_boundary(_desktop_sources())


@pytest.mark.parametrize('attack', ['new_process_host', 'run_identity_in_ide_host'])
def test_desktop_boundary_rejects_unreviewed_processes_and_agent_execution_identity(attack) -> None:
    sources = _desktop_sources()
    if attack == 'new_process_host':
        sources['lib/rogue-executor.ts'] = "import { spawn } from 'node:child_process'"
    else:
        sources['lib/lsp-client.ts'] += "\nconst runId = 'injected-run';\n"
    with pytest.raises(AssertionError):
        _assert_desktop_execution_boundary(sources)


def test_chat_terminal_keeps_its_existing_composition() -> None:
    """Chat routes file work through the existing AgentOS Local Runtime adapter."""
    chat_api = SRC.parents[1] / "agent" / "app" / "api" / "chat.py"
    catalog = SRC.parents[1] / "agent" / "app" / "tools" / "chat_catalog.py"
    runtime = SRC.parents[1] / "agent" / "app" / "tools" / "runtime.py"
    assert "get_chat_tool_runtime" in chat_api.read_text(encoding="utf-8")
    assert "LocalRuntimeToolExecutor" in catalog.read_text(encoding="utf-8")
    assert all(name in runtime.read_text(encoding="utf-8") for name in (
        "read_file", "list_files", "write_file", "patch_file"
    ))
    config = SRC.parents[1] / "agent" / "app" / "config.py"
    assert "CHAT_LEGACY_CONTAINER_TERMINAL_ENABLED: bool = False" in config.read_text(encoding="utf-8")


def test_chat_permission_policy_does_not_create_a_second_execution_authority() -> None:
    """Approval is a Chat gate; AgentOS Resource/Capability remains execution truth."""
    permission = SRC.parents[1] / "agent" / "app" / "tools" / "permissions.py"
    catalog = SRC.parents[1] / "agent" / "app" / "tools" / "chat_catalog.py"
    runtime = SRC.parents[1] / "agent" / "app" / "tools" / "runtime.py"
    permission_source = permission.read_text(encoding="utf-8")
    catalog_source = catalog.read_text(encoding="utf-8")
    runtime_source = runtime.read_text(encoding="utf-8")

    assert "ChatPermissionService" in catalog_source
    assert "LocalRuntimeToolExecutor" in catalog_source
    assert "CapabilityRegistry" not in permission_source + catalog_source
    assert "ResourceRegistry" not in permission_source + catalog_source
    assert "RuntimeEventBroker" not in permission_source + catalog_source
    assert "ResourceService(" not in permission_source + catalog_source
    assert "subprocess" not in permission_source
    assert "allowedRoot" not in permission_source
    assert "AgentRunContext" not in permission_source + runtime_source
    assert "APPROVAL_REQUIRED" in runtime_source
    assert "APPROVAL_RESOLVED" in runtime_source
    assert "allow_session" in permission_source
    assert "shell.exec" in permission_source


def test_chat_approval_contract_exposes_only_safe_display_fields() -> None:
    """Approval SSE/API data must not become a grant, credential, or host-root channel."""
    permission = SRC.parents[1] / "agent" / "app" / "tools" / "permissions.py"
    source = permission.read_text(encoding="utf-8")
    approval_block = source[source.index("class ApprovalRequest"):source.index("class ApprovalResolutionError")]
    assert "approvalId" in approval_block
    assert "toolCallId" in approval_block
    assert "capabilityId" in approval_block
    assert "relativePath" in approval_block
    assert "allowedRoot" not in approval_block
    assert "resourceId" not in approval_block
    assert "credentialId" not in approval_block


def test_memory_and_evolution_forbid_runtime_mutation_primitives() -> None:
    """Memory remains a service/store and evolution remains declarative policy data."""
    guarded_roots = (SRC / "components" / "memory", SRC / "components" / "evolution")
    forbidden_calls = {"exec", "eval", "compile"}
    for root in guarded_roots:
        for path in _python_sources(root):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            calls = {
                node.func.id
                for node in ast.walk(tree)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            }
            assert calls.isdisjoint(forbidden_calls), path


def test_v2_planner_core_contains_no_case_specific_domain_steps() -> None:
    """Golden scenarios belong in evals or Packs, never in the generic planner."""
    planner_root = SRC / "components" / "planner"
    source = "\n".join(path.read_text(encoding="utf-8") for path in _python_sources(planner_root))
    forbidden_case_terms = {
        "源网荷储", "医院智慧门诊", "法律合同审查", "工业园区能源优化",
    }
    assert forbidden_case_terms.isdisjoint(source)
