# 知弈 AgentOS

<p align="center">
  <strong>面向超长程复杂任务的动态异构群体智能运行时</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/status-stable%20candidate-22c55e?style=for-the-badge" alt="Stable candidate">
  <img src="https://img.shields.io/badge/license-MIT-blue?style=for-the-badge" alt="License">
</p>

---

## 项目简介

知弈 AgentOS 面向荣耀终端股份有限公司发布的挑战杯赛题 **XH-202631：面向超长程复杂任务的动态异构群体智能架构与深度协同推理技术**。

知弈的核心答案是 **Agentic Computation Graph（ACG）**。系统把 Step、Agent、Skill、Memory、Evidence 和 Control 建模为有类型节点，把依赖、通信、控制、读写和证据支撑建模为不同类型的边；再由唯一的 WKN `WorkflowRuntime` 完成规划、调度、执行、恢复和审计。

---

## 技术栈

| 层次 | 技术 |
|:---|:---|
| 前端 | Vue 3 + Milan Workbench |
| 网关 | Spring Boot 3.2 + Spring Security |
| 运行时 | FastAPI |
| 核心内核 | WKN AgentOS (Python) |
| 桌面端 | Tauri |

---

## 核心能力

### 1. ACG 动态异构拓扑

- `DEPENDENCY` 边决定就绪集与并行执行
- `COMMUNICATION` 边声明允许的数据通道
- `CONTROL_FLOW` 表达条件、分支、汇聚和 Review
- `GraphPatch` 在安全 review barrier 上进行版本化、不可变拓扑变更

### 2. 低熵通信

Communication Broker 依据拓扑、字段白名单、作用域与熵预算向下游投递最小 `ContextPack`，Provenance 同步记录生产者、消费者、字段、校验和及证据引用。

### 3. 长程记忆与引用式状态

Workflow、Checkpoint、Execution Value、Evidence Memory、Provenance、Decision 分库存储。Run DTO 只返回运行摘要和引用，正文通过 `outputRef` 解引用。

### 4. 自主恢复

支持 Checkpoint CAS、Recovery Recipe、contract repair、alternate rebind，在故障或需求变化后保持同一 run_id 继续执行。

### 5. 多模型与外部能力治理

模型调用在冻结的 execution binding 下执行，支持能力与版本约束、异步健康刷新、主备 failover、key rotation、超时与重试。

---

## 快速开始

### Windows 11 + Docker Desktop

```powershell
# 复制环境配置
Copy-Item .config/env/windows.example .env.windows

# 初始化密钥
py -3 -m ops.scripts.infra.init_secrets .secrets/kinlin-win-dev-001

# 启动服务
.\ops\scripts\infra\windows\up.ps1 -Build
```

默认入口：<http://127.0.0.1:8080>

### Linux / macOS

```bash
cp .env.example .env
python3 -m ops.scripts.infra.init_secrets .secrets/kinlin-dev-local
export KINLIN_DEPLOYMENT_ID=kinlin-dev-local
export KINLIN_SECRETS_DIR="$PWD/.secrets/kinlin-dev-local"
./ops/scripts/dev.sh up
```

---

## 项目结构

```
知弈 AgentOS
├── apps/
│   ├── agent/                   # FastAPI 应用、领域 Agent Packs
│   ├── agentOS/                 # WKN Runtime、执行内核与合同
│   ├── backend/                 # Spring Security 网关
│   ├── frontend/                # Milan Vue 3 工作台
│   └── desktop/                 # Tauri 桌面客户端
├── ops/
│   ├── docker/                  # 镜像、入口脚本
│   ├── deploy/                  # 离线部署包
│   └── scripts/                 # 部署、诊断脚本
├── .config/compose/             # Docker Compose 覆盖配置
├── .config/env/                 # 环境变量模板
├── compose.yaml                 # 根目录生产 Compose
└── docs/                        # 架构与交付文档
```

---

## 领域 Pack

| Pack | 说明 |
|:---|:---|
| Legal | 合同审查、案例分析、法规检索 |
| Programmer | 代码生成、需求分析、代码库搜索 |
| Education | 教案生成、作业批改、学情诊断 |
| Writer | 故事大纲、角色关系、内容创作 |
| Industrial | 工业设计能力 |

---

## 验证基线

| 测试层 | 结果 |
|:---|---:|
| AgentOS Kernel | **187 passed** |
| Python Application / Packs | **102 passed** |
| Spring Gateway | **132 passed** |
| Frontend | **115 tests passed** |

---

## 文档

- [项目设计方案](docs/01-赛题与项目概述/01-项目设计方案.md)
- [技术选型报告](docs/01-赛题与项目概述/02-技术选型与技术路线报告.md)
- [ACG 动态群体智能引擎设计](docs/02-架构设计/05-ACG动态群体智能引擎技术设计.md)
- [文档总索引](docs/README.md)

---

## License

MIT © 知弈 Team

---

<p align="center">
  <sub>一个内核 · 一个 Runtime · 一个 AgentOS v2 API</sub>
</p>