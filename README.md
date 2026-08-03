
<p align="center">
  <img src="frontend/public/logo.png" alt="知弈 AgentOS Logo" width="120" />
</p>

<h1 align="center">知弈 AgentOS</h1>

<p align="center">
  <strong>面向下一代 AI Agent 基础设施<br>聚焦企业复杂任务场景，构建多 Agent 分工协同、可复用、可观测的端到端任务闭环系统</strong>
</p>

<p align="center">
  <a href="#-快速开始"><img src="https://img.shields.io/badge/version-1.0.0--alpha-6366f1?style=for-the-badge" alt="Version"></a>
  <a href="#-核心特性"><img src="https://img.shields.io/badge/status-active-22c55e?style=for-the-badge" alt="Status"></a>
  <img src="https://img.shields.io/badge/core%20tests-185%20passed-22c55e?style=for-the-badge" alt="Tests">
  <img src="https://img.shields.io/badge/license-MIT-blue?style=for-the-badge" alt="License">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Frontend-Vue%203-42b883?style=flat-square&logo=vue.js" alt="Vue 3">
  <img src="https://img.shields.io/badge/Backend-Spring%20Boot%203.2-6db33f?style=flat-square&logo=spring" alt="Spring Boot">
  <img src="https://img.shields.io/badge/Runtime-FastAPI-009688?style=flat-square&logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/Core-Python%203.12-3776ab?style=flat-square&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey?style=flat-square" alt="Platform">
</p>

---

## 简介

知弈 AgentOS 是一套**群体智能运行时操作系统**——当 AI 从单轮问答走向自主执行，复杂任务需要的不再是更长的上下文窗口，而是一个能描述、调度、通信、记忆和自我修复的工程运行时。

我们将问题定义为：

> **给定自然语言任务目标、约束、风险与资源预算，如何即时构造一个可执行、可观察、可恢复、可审计的多智能体计算图？**

系统的核心答案是 **Agentic Computation Graph (ACG)**——一种将 Step、Agent、Skill、Memory、Evidence 和 Control 建模为有类型节点，将执行依赖、通信、控制、读写与支撑关系建模为不同类型边的统一中间表示。围绕 ACG，系统建立了 JIT 混合规划、就绪集并行调度、字段级低熵通信、数据血缘追溯，以及由故障注入、检查点和局部重规划构成的自愈闭环。

---

## 为什么选择知弈？

现有技术范式面临三重结构性瓶颈：

| 瓶颈 | 表现 | 知弈的解法 |
|:---|:---|:---|
| **注意力稀释与记忆坍缩** | 单体智能体在超长上下文膨胀中遗忘关键信息 | 四级记忆体系 + Checkpoint 断点续跑 |
| **Token 冗余爆炸** | 全连接广播式通信导致决策噪声级联放大 | 字段级低熵通信，节省率可达 99.65% |
| **缺乏动态路由与容错** | 静态流水线面对异常只能从头重跑 | ACG 拓扑 + 故障注入 + 局部重规划 |

**知弈的定位不是 LLM、RAG、多 Agent 等技术的简单叠加，而是通过统一运行时内核对各类能力进行封装、规划和调度。**

---

## 核心架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Vue 3 工作台 (Frontend)                    │
│          Agent/Chat 交互 · ACG 拓扑可视化 · 治理面板          │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│              Spring Boot 业务与安全网关 (Backend)              │
│            认证 · 用户 API · AI 安全 · 业务编排                │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                FastAPI Agent Runtime (Agent)                  │
│         模型路由 · RAG 知识服务 · 领域 Agent Pack               │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                   AgentOS Core (Python)                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐ │
│  │  JIT 混合  │  │  ACG 蓝图 │  │ 就绪集并行 │  │  治理与评估   │ │
│  │   规划器   │  │  图算法   │  │   执行器   │  │ Trace/Review │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘ │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │     字段级低熵通信 (ContextAssembler + ProvenanceLedger)    │ │
│  └──────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## 核心特性

<table>
  <tr>
    <td width="50%">
      <h4>Agentic Computation Graph</h4>
      <p>将复杂任务编译为有类型计算图。6 种节点类型（Step、Agent、Skill、Memory、Evidence、Control）和 6 种边类型（DEPENDENCY、COMMUNICATION、CONTROL_FLOW、EXECUTION、READ/WRITE、SUPPORT），让调度、通信、记忆和治理各司其职。</p>
    </td>
    <td width="50%">
      <h4>JIT 混合规划</h4>
      <p>"静态优选，动态补位"——高频路径复用经过验证的模板，未知路径即时动态生成 ACG。执行层不区分蓝图来源，兼顾效率与灵活性。</p>
    </td>
  </tr>
  <tr>
    <td>
      <h4>字段级低熵通信</h4>
      <p>告别全连接广播。下游 Step 通过 <code>inputSpec</code> 字段契约声明所需数据，<code>ContextAssembler</code> 提取最小子集。菱形图压力测试中 token 节省率达 <strong>99.65%</strong>。</p>
    </td>
    <td>
      <h4>工作流升格</h4>
      <p>既有 YAML 线性工作流一键升格为完整 ACG——步骤映射为 StepNode，依赖映射为 DEPENDENCY 边，自动获得并行调度、字段通信、数据血缘等全部运行时能力。</p>
    </td>
  </tr>
  <tr>
    <td>
      <h4>故障自愈 (Harness)</h4>
      <p>混沌工程引入多智能体运行时。故障注入 → Checkpoint 快照 → 局部重规划 → 同 run_id 续跑。长程任务从"从头重跑"提升为"精确定位、局部恢复"。</p>
    </td>
    <td>
      <h4>可观测与可审计</h4>
      <p>Trace 时间线记录每个调度、启动、数据消费和生产事件。ProvenanceLedger 提供双向血缘追溯——"结论从何而来"与"数据影响了何处"，天然可审计。</p>
    </td>
  </tr>
  <tr>
    <td>
      <h4>多 Agent 分工协同</h4>
      <p>异构角色通过能力标签自动匹配任务。CognitiveRouter 在无模板命中时基于能力、负载、成本和网络通信成本进行加权评分与动态组网。</p>
    </td>
    <td>
      <h4>隐私协同 (联邦学习)</h4>
      <p>可插拔的隐私协同子系统——各节点本地训练，仅上传受保护的参数。FedAvg 聚合 + 梯度裁剪 + 差分隐私，"数据不动，模型协同"。</p>
    </td>
  </tr>
</table>

---

## 比赛背景

本项目参加**第十九届"挑战杯"全国大学生课外学术科技作品竞赛"揭榜挂帅"擂台赛**（题目编号：**XH-202631**），由荣耀终端股份有限公司发榜。

题目要求构建一种"具备全局动态任务编排以及自适应网络拓扑流转机制的智能体生态网络"，重点攻克超长周期下的上下文连续性保持、神经符号协同推理与低熵通信难题。

### 赛题交付物矩阵

| 赛题要求 | 对应机制 | 状态 |
|:---|:---|:---:|
| 超长程上下文连续性与记忆保持 | Task 状态机 + Memory 节点 + Checkpoint 断点续跑 | ✅ |
| 动态异构拓扑与低熵通信 | ACG 蓝图 + CognitiveRouter + 字段契约 + ContextAssembler | ✅ |
| 端-边-云异构资源自适应调度 | ResourceProfile + 多目标效用评分 + 隐私硬约束 | 🚧 |
| 典型产业场景可运行系统验证 | 律师合同审查 6 阶段端到端链路 | ✅ |
| 异常/节点失效无人工干预恢复 | FaultInjector + Checkpoint + local_replan | ✅ |
| 中间决策过程与推理轨迹展示 | Trace 时间线 + ACG 拓扑可视化 + 数据血缘面板 | ✅ |

> 完整方案文档：[比赛方案](<claude context/比赛方案.txt>)

---

## 快速开始

### 前置条件

- **Windows 11** + Docker Desktop (Linux containers)
- 或 **Linux / macOS** + Docker
- Git

### Windows 一键部署

```powershell
# 1. 配置环境
Copy-Item .env.windows.example .env.windows
python -m scripts.infra.init_secrets .secrets/kinlin-win-dev-001

# 2. 配置模型 API Key（至少配置一个）
# 将 DeepSeek API Key 写入 .secrets/kinlin-win-dev-001/deepseek_api_key
# 或将 DashScope API Key 写入 .secrets/kinlin-win-dev-001/dashscope_api_key

# 3. 启动全栈服务
.\scripts\infra\windows\up.ps1 -Build
```

打开 **http://127.0.0.1:8080**，首次使用自行注册账号。

### 前端热更新开发

```powershell
.\scripts\infra\windows\up.ps1 -DebugPorts
cd frontend
npm ci
$env:DEV_BACKEND_PROXY_TARGET = "http://127.0.0.1:18080"
npm run dev
```

前端开发服务位于 **http://localhost:3000**，通过代理调用容器中的完整后端能力。

### Linux / macOS

```bash
cp .env.example .env
python -m scripts.infra.init_secrets .secrets/kinlin-dev-local
export KINLIN_DEPLOYMENT_ID=kinlin-dev-local
export KINLIN_SECRETS_DIR="$PWD/.secrets/kinlin-dev-local"
./dev.sh up
```

---

## 测试

```powershell
$env:PYTHONPATH = "$PWD\agentOS\src;$PWD\agent"
python -m pytest agentOS/tests -q    # AgentOS Core: 51 passed
python -m pytest agent/tests -q       # Agent Runtime: 134 passed, 1 skipped
```

| 测试集 | 结果 | 覆盖范围 |
|:---|---:|---|
| AgentOS Core | **51 passed** | ACG 节点/边模型、图算法、工作流升格、蓝图校验 |
| Agent Runtime / API / Pack | **134 passed**, 1 skipped | 规划器、通信器、执行器、合同审查 Pack、故障注入与自愈 |
| **合计** | **185 passed**, 1 skipped | — |

---

## 项目结构

```text
知弈 AgentOS
├── agentOS/                    # AgentOS Core — 内核运行时
│   └── src/agentos/core/
│       ├── acg/                #   ACG 蓝图 (节点/边/图操作/升格)
│       ├── planning/           #   JIT 混合规划 (意图解析/模板匹配/认知路由)
│       ├── communication/      #   低熵通信 (字段契约/装配/血缘)
│       ├── execution/          #   就绪集并行执行 (执行器/适配器/故障注入)
│       └── governance/         #   治理 (Trace/Checkpoint/Review/评估)
├── agent/                      # Agent Runtime + 领域 Packs
│   ├── app/                    #   FastAPI 运行时
│   └── packs/                  #   领域 Agent Pack (法律/教育/投研/…)
├── backend/                    # Spring Boot 业务与安全网关
├── frontend/                   # Vue 3 工作台 + ACG 可视化面板
├── docker/                     # Docker Compose 基线
├── scripts/infra/              # 部署、预检、备份脚本
└── docs/                       # 完整技术文档
```

---

## 文档

| 文档 | 说明 |
|:---|:---|
| [文档总索引](docs/README.md) | 所有文档的导航入口 |
| [项目设计方案](docs/01-赛题与项目概述/01-项目设计方案.md) | 完整方案阐述 |
| [技术选型报告](docs/01-赛题与项目概述/02-技术选型与技术路线报告.md) | 技术选型与路线 |
| [AgentOS 架构说明](docs/02-架构设计/01-AgentOS架构说明.md) | 总体架构设计 |
| [核心代码层次](docs/02-架构设计/02-知弈AgentOS-Core代码层次架构图.md) | 代码架构 |
| [ACG 引擎技术设计](docs/02-架构设计/05-ACG动态群体智能引擎技术设计.md) | ACG 引擎深度设计 |
| [律师 AgentOS 设计](docs/02-架构设计/06-知弈律师AgentOS技术设计文档.md) | 合同审查验证场景 |
| [ACG 测试样例](docs/04-演示与交付/02-acg-test-samples.md) | 测试用例 |
| [ACG 引擎验证报告](docs/04-演示与交付/03-acg-engine-final-report.md) | 验证结果 |

---

## 路线图

| 状态 | 能力域 |
|:---:|:---|
| ✅ **已实现** | ACG 数据结构与图算法、工作流升格、JIT 混合规划、就绪集并行执行、字段级低熵通信与 ProvenanceLedger、Trace、Review、Checkpoint、故障注入与自愈恢复、合同审查 Pack、ACG 可视化面板 |
| 🚧 **实验阶段** | 联邦学习训练闭环 (FedAvg/梯度裁剪/差分隐私/模型版本治理)、联邦 RAG 参数聚合、调度器 ResourceProfile 与多目标效用评分 |
| 📋 **规划中** | 端-边-云异构资源调度执行链路、完整四级记忆体系、生产级多租户与 RBAC、OpenTelemetry 遥测、高可用 Workflow Store、国产化环境部署验证 |

---

## 重要声明

- 知弈 AgentOS 是**工程原型**而非商业产品。合同审查输出是辅助材料，不构成正式法律意见。
- Workflow Store 当前为单实例 SQLite，代表原型阶段约束，非生产级方案。
- 端-边-云调度器执行链路、联邦学习多机构部署验证、四级记忆中的后两级为后续工作。
- 文档中的性能数字来自受控测试样例，不等同于生产基准。

---

## License

MIT © 知弈 Team

---

<p align="center">
  <sub>路还很长。下一阶段需要在更多场景、更大规模的测试中，诚实地验证这些设计假设哪些能站住，哪些需要重来。我们期待这个过程。</sub>
</p>

<p align="center">
  <sub>Made by 知弈 Team · 2026</sub>
</p>
