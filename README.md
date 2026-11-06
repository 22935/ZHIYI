<p align="center">
  <img src="docs/assets/brand/show.png">
</p>

<p align="center">
  <strong>面向下一代 AI Agent 基础设施</strong><br>
  <sub>让多 Agent 在同一个可规划、可通信、可恢复、可审计的执行真源中完成复杂工作</sub>
</p>

<p align="center">
  <a href="#快速开始"><img src="https://img.shields.io/badge/version-1.0.0--candidate-6366f1?style=for-the-badge" alt="Version"></a>
  <a href="#核心特性"><img src="https://img.shields.io/badge/status-stable%20candidate-22c55e?style=for-the-badge" alt="Status"></a>
  <img src="https://img.shields.io/badge/core%20tests-1730%20cases-22c55e?style=for-the-badge" alt="Tests">
  <img src="https://img.shields.io/badge/license-MIT-blue?style=for-the-badge" alt="License">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Frontend-Vue%203-42b883?style=flat-square&logo=vue.js" alt="Vue 3">
  <img src="https://img.shields.io/badge/Backend-Spring%20Boot%203.2-6db33f?style=flat-square&logo=spring" alt="Spring Boot">
  <img src="https://img.shields.io/badge/Runtime-FastAPI-009688?style=flat-square&logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/Core-Python%203.14-3776ab?style=flat-square&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey?style=flat-square" alt="Platform">
</p>

---

## 简介

知弈 AgentOS 是一套**群体智能运行时操作系统**——当 AI 从单轮问答走向自主执行，复杂任务需要的不再是更长的上下文窗口，而是一个能描述、调度、通信、记忆和自我修复的工程运行时。

我们将问题定义为：

<p align="center">
  <em>给定自然语言任务目标、约束、风险与资源预算，如何即时构造一个可执行、可观察、可恢复、可审计的多智能体计算图？</em>
</p>

系统的核心答案是 **Agentic Computation Graph (ACG)**——一种将 Step、Agent、Skill、Memory、Evidence 和 Control 建模为有类型节点，将执行依赖、通信、控制、读写与支撑关系建模为不同类型边的统一中间表示。

当前版本由唯一的 `ExecutionRuntime` 承担执行真源：Planner 产出 Blueprint，Compiler 冻结 Package、合同与 Binding，ExecutionGraph 推进就绪集与并行超步，NodeRunner 装配最小 ContextPack 并提交引用；Checkpoint、Provenance、Decision 与 Identity V2 分别负责恢复、追溯、审计与查询投影。

---

## 为什么选择知弈？

现有技术范式面临三重结构性瓶颈：

| 瓶颈                           | 表现                                     | 知弈的解法                                                   |
| :----------------------------- | :--------------------------------------- | :----------------------------------------------------------- |
| **注意力稀释与记忆坍缩** | 单体智能体在超长上下文膨胀中遗忘关键信息 | 六类独立 Store + Checkpoint CAS + 引用式输出                 |
| **Token 冗余爆炸**       | 全连接广播式通信导致决策噪声级联放大     | Communication Broker：字段白名单 + 熵预算 + 最小 ContextPack |
| **缺乏动态路由与容错**   | 静态流水线面对异常只能从头重跑           | ACG 动态拓扑 + GraphPatch + 局部恢复与恢复配方               |

<p align="center">
  <strong>知弈的定位不是 LLM、RAG、多 Agent 等技术的简单叠加，而是通过统一运行时内核对各类能力进行封装、规划和调度。</strong>
</p>

---

## 核心架构

<p align="center">
  <img src="docs/架构设计/架构图/知弈AgentOS_ACG总体架构.png" alt="知弈 AgentOS 六层总体架构" width="100%" />
</p>

<p align="center">
  <sub>六层能力视图：目标层 → 认知规划 → 群体组织 → 执行引擎 → 自愈恢复 → 基础设施；右侧为交付物与全链路可追溯能力</sub>
</p>

## 核心特性

<table>
  <tr>
    <td width="50%" align="center">
      <h4>Agentic Computation Graph</h4>
      <p>将复杂任务编译为有类型计算图。6 种节点类型（Step、Agent、Skill、Memory、Evidence、Control）和 6 种边类型（DEPENDENCY、COMMUNICATION、CONTROL_FLOW、READ/WRITE、SUPPORT、EXECUTION），让调度、通信、记忆和治理各司其职。</p>
    </td>
    <td width="50%" align="center">
      <h4>规划提交与图修订 (S01–S03)</h4>
      <p>规划不再直接改图：Planner 产出候选，PlanningCommit 负责持久化接受，GraphRevision 负责版本化修订，ActivationAuthority 负责唯一激活，CheckpointIdentity 负责恢复时的身份交接。</p>
    </td>
  </tr>
  <tr>
    <td align="center">
      <h4>字段级低熵通信</h4>
      <p>告别全连接广播。下游节点只声明自己需要的字段，Communication Broker 按字段白名单与熵预算投递最小 <code>ContextPack</code>，并同步记录生产者、消费者、字段、校验和与证据引用。</p>
    </td>
    <td align="center">
      <h4>引用式状态与六类 Store</h4>
      <p>Workflow、Checkpoint、Execution Value、Memory、Provenance、Decision 分库存储。Run DTO 只返回摘要与引用，正文通过 <code>outputRef</code> 解引用，长程状态不会被模型原文撑爆。</p>
    </td>
  </tr>
  <tr>
    <td align="center">
      <h4>自愈与断点恢复</h4>
      <p>故障或需求变化 → guarded runtime 分类与审计 → Checkpoint CAS → 恢复配方 / 契约修复 / 备用绑定 → 必要时 GraphPatch，保持同一 <code>run_id</code> 与引用归属继续执行。</p>
    </td>
    <td align="center">
      <h4>模型运行时治理</h4>
      <p>模型调用在冻结的 execution binding 下执行：能力与版本约束、异步健康刷新、主备 failover、key rotation、统一超时重试；<code>commitId</code> 在重试中保持不变并作为外部幂等键。</p>
    </td>
  </tr>
  <tr>
    <td align="center">
      <h4>端-边-云资源调度</h4>
      <p>ResourceProfile 分层画像、远程资源注册、资源级 HMAC 签名观测、观测序号校验、约束过滤、租约与快照版本确认、远程执行 Adapter，以及边缘失败后的云端重绑定。</p>
    </td>
    <td align="center">
      <h4>可视化与可审计</h4>
      <p>Milan 工作台提供 Run history、Graph、Trace、Provenance、Checkpoint、Review 与 Output 视图；高风险节点可进入 <code>WAITING_REVIEW</code>，审核后从原运行恢复，而不是回到任意历史检查点。</p>
    </td>
  </tr>
</table>

<p align="center">
  <img src="docs/架构设计/架构图/知弈AgentOS-ACG架构图.png" alt="ACG 动态群体智能引擎架构" width="100%" />
</p>

<p align="center">
  <sub>ACG 引擎全景：端到端闭环、三层解耦、规划与编译、计算图模型、就绪集并行执行、低熵通信与自愈闭环</sub>
</p>

---

## 比赛背景

本项目参加**"挑战杯"全国大学生课外学术科技作品竞赛"揭榜挂帅"擂台赛**（题目编号：**XH-202631**），由荣耀终端股份有限公司发榜。

题目要求构建一种"具备全局动态任务编排以及自适应网络拓扑流转机制的智能体生态网络"，重点攻克超长周期下的上下文连续性保持、神经符号协同推理与低熵通信难题。

### 赛题交付物矩阵

| 赛题要求                     | 对应机制                                                                   | 状态 |
| :--------------------------- | :------------------------------------------------------------------------- | :--: |
| 超长程上下文连续性与记忆保持 | 六类 Store + Checkpoint CAS + Evidence Memory + 引用式输出                 |  ✅  |
| 动态异构拓扑与低熵通信       | ACG + conditional routing + 并行超步 + Communication Broker + Provenance   |  ✅  |
| 端-边-云异构资源自适应调度   | ResourceProfile + 资源注册 + 签名观测 + 租约 + 远程 Adapter + 云端重绑定   |  🚧  |
| 典型产业场景可运行系统验证   | 通用 ACG 执行 + 本机工作区开发/测试纵切                                     |  🚧  |
| 异常/节点失效无人工干预恢复  | Checkpoint + 恢复配方 + 契约修复 + GraphPatch + review barrier             |  ✅  |
| 中间决策过程与推理轨迹展示   | Trace + Provenance + Checkpoint + Review + Output                          |  ✅  |

> 端-边-云目前完成的是**位置选择**基础链路；神经网络层级切分尚未实现，真实多设备部署与故障演示仍待验收。当前保留通用 ACG 执行与本机工作区纵切；职业能力 Pack 已从当前树删除。
>
> 完整方案文档：[比赛方案](docs/赛题与项目概述/比赛方案.pdf)

---

## 快速开始

### 前置条件

- **Windows 11**（当前唯一支持的本地原生持久运行形态；不再需要 Docker Desktop / WSL 容器）
- JDK 21（N03 运行时；后端编译目标 Java 17）、Maven、Node.js 18+、Python 3.14
- Git

PostgreSQL 15.19、Memurai 4.1.2 与 Python 3.14 venv 由
[`prepare_persistent_dependencies.py`](ops/scripts/infra/windows/native/prepare_persistent_dependencies.py)
准备到 `%LOCALAPPDATA%\ZhiyiNative\`，不安装 Windows 服务、不修改系统 PATH。
运行形态、数据布局与故障恢复见 [N03 运行说明](ops/scripts/infra/windows/native/README-N03.md)。

### Windows 原生启动（N03）

```powershell
# 1. 首次：Python 依赖与本地 PostgreSQL/Memurai 依赖包
python -m venv "$env:LOCALAPPDATA\ZhiyiNative\python"
$py = "$env:LOCALAPPDATA\ZhiyiNative\python\Scripts\python.exe"
& $py -m pip install --require-hashes --only-binary=:all: -r apps/agent/requirements.lock -r apps/agent/requirements.native-tools.lock
& $py ops/scripts/infra/windows/native/prepare_persistent_dependencies.py

# 2. 构建后端 jar
Push-Location apps/backend
mvn -DskipTests package
Pop-Location

# 3. 首次：初始化独立 home（模型 Key 由 DPAPI 保存；路径仅首次可指定）
$entry = '.\ops\scripts\infra\windows\native\persistent.ps1'
$homeDir = "$env:LOCALAPPDATA\ZhiyiNative\default"
& $entry init -HomeDir $homeDir -Python $py -ProviderKeyFile 'C:\私有路径\deepseek_api_key'

# 4. 日常启停（含 Electron 桌面）
& $entry up -HomeDir $homeDir -Python $py -Desktop
& $entry status -HomeDir $homeDir -Python $py
& $entry down -HomeDir $homeDir -Python $py
```

默认 loopback 端口：PostgreSQL 15432、Memurai 16379、Python 18761、知行 Host 18765、
Java 18080、Vite 15200；`-Desktop` 额外使用 Chromium CDP 19222。
首次通过桌面注册/登录；后续 `up` 复用同一 home、同一身份与全部数据，不重建数据库。

### 桌面热更新开发

N03 栈运行时（无需 `-Desktop`）：

```powershell
& $entry up -HomeDir $homeDir -Python $py
.\ops\scripts\start-desktop-hot.ps1
```

热更新链固定 Vite 15100，代理默认直连 N03 Java 18080；关闭桌面窗口即结束本次开发运行。

---

## 测试

```powershell
Set-Location apps/agentOS
python -m pytest tests -q

Set-Location ../agent
python -m pytest tests -q

# Spring 后端的真实 PostgreSQL/Redis 契约测试由测试 JVM 自管临时实例，不需要 Docker
Set-Location ../backend
mvn -B -ntp test

Set-Location ../frontend
npm ci
npm run test
```

### 当前套件规模

| 测试集                      |                         规模 | 覆盖范围                                                              |
| :-------------------------- | ---------------------------: | :-------------------------------------------------------------------- |
| AgentOS Kernel              |         **1730 cases** | ACG 节点/边模型、图执行、通信、记忆、恢复、规划提交、图修订、资源调度 |
| Agent Runtime / API / Packs |      见 `apps/agent/tests` | 规划器、通信器、执行器、领域 Packs、SSE 流式事件                      |
| Spring Gateway              | 见 `apps/backend/src/test` | 鉴权、安全契约、可观测性契约、架构守卫、自管 PG/Redis 集成测试       |
| Milan Frontend              |     见 `apps/frontend/src` | 视图、组件、状态与交互回归                                            |

### 最近一次完整收束基线（2026-08-19）

| 测试集                                      |                                                            结果 |
| :------------------------------------------ | --------------------------------------------------------------: |
| AgentOS Kernel                              |                                            **187 passed** |
| Python Application / Packs / AgentOS v2 API |                                 **102 passed**, 1 skipped |
| Spring Gateway                              |                                            **132 passed** |
| Milan Frontend                              |                            **24 files, 115 tests passed** |
| N03 原生栈健康检查                          | PostgreSQL / Memurai / AI / Host / Java / Vite 全部 UP          |

> 内核套件已从 187 项增长到 1730 项。代码变更后必须重新执行，历史数字不代表当前结果。

---

## 项目结构

```text
知弈 AgentOS
├── apps/
│   ├── agentOS/                # WKN 内核 — 唯一执行真源
│   │   └── src/
│   │       ├── runtime/        #   ExecutionRuntime / 身份生命周期
│   │       ├── components/     #   Planner / Executor / Communicator / Recovery
│   │       ├── storage/        #   六类 Store 与查询投影
│   │       └── support/        #   Packs / Skills / ACG 支撑结构
│   ├── agent/                  # FastAPI 运行时
│   │   ├── app/                #   Composition Root · API · 适配器
│   │   └── packs/              #   通用 Agent Pack（当前仅 workspace）
│   ├── backend/                # Spring Boot 业务与安全边界
│   ├── frontend/               # Vue 3 · Milan 工作台 + ACG 可视化
│   └── desktop/                # Electron 桌面壳
├── contracts/                  # AgentOS v2 接口契约
├── benchmark/                  # 基准与冒烟脚本
├── tools/                      # 端-边-云演示 / 终端调试界面
├── ops/                        # Windows 原生运行/检查脚本（N01A/N03）
└── docs/                       # 架构、开发记录与交付材料
```

本机运行数据不在仓库内，固定位于 `%LOCALAPPDATA%\ZhiyiNative\default\`（PostgreSQL cluster、
Memurai RDB/AOF、SQLite Store、uploads、workspace、Electron 用户数据与 DPAPI 凭据）。
```

---

## 文档

| 文档                                                                                                    | 说明                               |
| :------------------------------------------------------------------------------------------------------ | :--------------------------------- |
| [文档总索引](docs/README.md)                                                                             | 所有文档的导航入口                 |
| [当前架构图](docs/架构设计/kinlin-agentos-current-architecture.md)                                       | 请求链、执行内核、持久化与查询投影 |
| [核心代码层次](docs/架构设计/02-知弈AgentOS-Core代码层次架构图.md)                                       | 代码架构与模块边界                 |
| [ACG 引擎技术设计](docs/架构设计/05-ACG动态群体智能引擎技术设计.md)                                      | ACG 引擎深度设计                   |
| [历史：律师 AgentOS 设计](docs/架构设计/06-知弈律师AgentOS技术设计文档.md)                               | 已下线的合同审查场景（历史设计）   |
| [N03 原生运行说明](ops/scripts/infra/windows/native/README-N03.md)                                       | 依赖、启停、数据布局与冷备份       |
| [Windows 原生运行链（N01A ~ N03 + 移除 Docker）](docs/开发记录/PR-N01A-N03-Windows原生运行链-合并记录.md)  | 零 Docker 原生形态与移除 Docker 的证据 |
| [PromptRuntime 与系统提示词清单](docs/开发记录/PromptRuntime与系统提示词清单-合并记录.md)                 | 提示词权威、信任封装与审计身份     |
| [WKN-C4-Milan 稳定集成报告](apps/agentOS/docs/系统迁移档案/阶段迁移报告/WKN-C4-Milan稳定集成总结报告.md) | 三线收束证据                       |
| [Docker 基础设施 RFC（历史，已废弃）](docs/架构设计/07-Docker基础设施重构RFC-v1.1.md)                     | 旧容器部署底座的冻结设计，仅作历史 |

---

## 路线图

|        状态        | 能力域                                                                                                                                                                                                                                                             |
| :-----------------: | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ✅ **已实现** | 单一 `ExecutionRuntime` 与执行真源、ACG 动态拓扑与并行超步、低熵通信与 Provenance、六类 Store 与 `outputRef` 引用式状态、Checkpoint/恢复/契约修复/GraphPatch、S01–S03 规划提交与图修订协议、Milan 可视化工作台、本机工作区纵切、Windows 原生持久栈（N03）与 Electron 桌面收口 |
| 🚧 **进行中** | 第二个高完成度跨领域长任务、数千步长程稳定性与 Token/耗时基准、浏览器级 `WAITING_REVIEW → approve → resume` 与真实模型/工具验收                                                                                                                                |
| 📋 **规划中** | 真实端-边-云多设备调度演示、模型层切分、生产级密钥轮换与资源凭据生命周期、核心算法伪代码与对照实验归档、演示视频与提交包校验                                                                                                                                       |

---

## 重要声明

- 知弈 AgentOS 当前是**比赛稳定候选与工程原型**，不等同于生产级商业系统。合同审查输出是辅助材料，不构成正式法律意见。
- 六类运行 Store 当前使用独立 SQLite 文件，这是单实例部署选择，不代表已完成生产级横向扩展。
- 端-边-云目前完成的是**位置选择**基础链路：画像、注册、签名观测、约束调度、租约、远程 Adapter 与云端重绑定。真实多设备、生产级密钥轮换与故障演示仍需在隔离环境验收。
- **没有实现神经网络层级切分**：一次模型调用仍由一个完整执行节点在单个资源上完成。
- 远程资源观测必须同时通过服务级内部 Token 与资源级签名；生产环境缺少主密钥时拒绝启动。
- 测试数字中，1730 为当前内核套件规模，187 / 102 / 132 / 115 为 2026-08-19 历史基线，代码变化后必须重新执行。

---

## License

MIT © 知弈 Team

---

<p align="center">
  <sub><em>天地之功不可仓卒，艰难之业当累日也。</em><br>
  下一阶段需要在更多场景、更大规模的测试中，诚实地验证这些设计假设哪些能站住，哪些需要重来。我们期待这个过程。</sub>
</p>

<p align="center">
  <sub>Made by 知弈 Team · 2026</sub>
</p>
