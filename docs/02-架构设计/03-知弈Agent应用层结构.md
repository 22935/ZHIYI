# 知弈 Agent 应用层结构

# Zhiyi Agent Application Layer Structure

日期：2026-05-21

本文以当前迁移后的结构为准：`agentOS/src/agentos/` 是 AgentOS Core 的 canonical 包路径；`agent/` 是 Python 应用服务层；`agent/packs/` 承载具体领域 Pack。

---

## 1. 顶层结构

```text
Kinlin_AI/
  agentOS/
    src/
      agentos/
        core/
        agents/
        packs/
        skills/
        memory/
        stores/
        adapters/

  agent/
    app/
      main.py
      config.py
      paths.py
      api/
      services/
      ai_engine/
      middleware/
      data/

    packs/
      legal/
      education/
      programmer/
      writer/

    tests/
    agentos.py
```

---

## 2. Module 职责

| Module | 职责 | 约束 |
|---|---|---|
| `agentOS/src/agentos/core` | 管理 `AgentTask`、`WorkflowRun`、状态机、Trace、Checkpoint、审核和评估 | 不写行业逻辑，不直接依赖具体 Pack |
| `agentOS/src/agentos/agents` | 定义 `BaseAgent`、`AgentRunContext`、`AgentRegistry` | 只提供统一 Agent Interface 和注册机制 |
| `agentOS/src/agentos/packs` | 发现、校验、注册应用层 Pack | 默认扫描 `agent/packs/` |
| `agentOS/src/agentos/skills` | 定义 Skill Interface 与通用无领域 Skill | 法律、教育、程序员、作家等领域 Skill 放 Pack 内 |
| `agentOS/src/agentos/memory` | Workflow 中间上下文 | 与持久化 Store 分离 |
| `agentOS/src/agentos/stores` | Workflow 任务和运行记录的存储 Interface 与实现 | 当前保留内存与 SQLite 实现 |
| `agentOS/src/agentos/adapters` | 模型、检索、联邦增强等外部能力 Adapter | Core 可独立导入，应用服务惰性桥接 |
| `agent/app` | FastAPI、应用服务、传统 AI/RAG/语音/数字人能力 | 不承载 Core 生命周期逻辑 |
| `agent/packs` | 法律、教育、程序员、作家等领域能力包 | 通过 manifest 和 `register_pack` 注入 Core |

---

## 3. 当前运行链路

```text
POST /ai/core/tasks
  -> WorkflowRuntime.create_task()
  -> WorkflowRegistry.recommend()

POST /ai/core/workflows/runs
  -> WorkflowRuntime.start()
  -> Orchestrator.select_next_step()
  -> AgentRegistry.resolve()
  -> Application Pack Agent.run()
  -> TraceStore / CheckpointStore / ReviewManager
```

入口文件：`agent/app/api/agentos_core.py`

默认运行时：`agentOS/src/agentos/core/workflow_runtime.py`

Pack Registry：`agentOS/src/agentos/packs/registry.py`

当前已接入 Pack：`agent/packs/legal/`、`agent/packs/education/`、`agent/packs/programmer/`、`agent/packs/writer/`

---

## 4. 设计原则

```text
Core 管生命周期。
Pack 管行业能力。
Workflow 用配置定义步骤。
Agent 执行专业步骤。
Skill 提供原子能力。
Adapter 连接外部模型、检索、联邦和存储。
API Route 只做协议适配，不承载复杂执行逻辑。
```

检查线：

- 新增一个行业能力时，主要新增 `agent/packs/{pack_id}/`。
- `agentOS/src/agentos/core` 不出现法律、教育、程序员、作家等行业导入。
- Pack 可以依赖 Core Interface，Core 不反向依赖 Pack 实现。
- `agent/app/api/*` 保持薄路由，只做请求/响应转换。

---

## 5. 新增 Pack 的方式

1. 在 `agent/packs/{pack_id}/` 下创建 `manifest.yaml`。
2. 在 `workflows/` 中放置 Workflow YAML，声明步骤、Agent、审核节点和流转关系。
3. 在 `agents/` 中实现 `agentos.agents.BaseAgent` 子类。
4. 如果 Pack 有专属工具，放入 Pack 内的 `skills/`；跨 Pack 可复用能力先抽象为无领域接口，再放入 `agentOS/src/agentos/skills/`。
5. 在 Pack 的 `__init__.py` 中提供 `register_pack(agent_registry, workflow_registry)`。
6. 默认运行时通过 `agentos.packs.registry.register_installed_packs()` 加载启用的 Pack。
7. 为 Workflow、Agent 注册和关键执行路径补充测试。
