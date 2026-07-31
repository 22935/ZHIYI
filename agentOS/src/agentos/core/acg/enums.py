"""ACG（Agentic Computation Graph）核心枚举定义。

严格对应设计书附件一《ACG 节点完整结构信息表》，作为静态规划层与
动态运行时层共享的类型词表。
"""

from __future__ import annotations

from enum import Enum


class NodeType(str, Enum):
    """ACG 节点类型。

    - STEP: 最小执行单元，描述具体任务步骤。
    - AGENT: 智能体节点，承担执行职责，一个 Agent 可执行多个 Step。
    - SKILL: 技能节点，描述可被 Agent 调用的原子能力。
    - MEMORY: 记忆节点，提供上下文状态。
    - EVIDENCE: 证据节点，记录推理依据与可信证据。
    - CONTROL: 控制节点，负责流程控制与群体协调。
    """

    STEP = "step"
    AGENT = "agent"
    SKILL = "skill"
    MEMORY = "memory"
    EVIDENCE = "evidence"
    CONTROL = "control"


class EdgeType(str, Enum):
    """ACG 边类型。

    - DEPENDENCY: 任务依赖，决定 Step 的执行先后（执行器据此计算就绪集）。
    - COMMUNICATION: 通信关系，描述数据从上游输出端口流向下游输入端口。
    - CONTROL_FLOW: 控制流，由 Control 节点驱动的分支/循环/汇聚。
    - EXECUTION: Agent 节点到 Step 节点的执行绑定边。
    - WRITE: Step 写入 Memory 节点。
    - READ: Memory 节点供给下游 Step 读取。
    - SUPPORT: Evidence 节点支撑消费它的 Step。
    """

    DEPENDENCY = "dependency"
    COMMUNICATION = "communication"
    CONTROL_FLOW = "control_flow"
    EXECUTION = "execution"
    WRITE = "write"
    READ = "read"
    SUPPORT = "support"


class ControlType(str, Enum):
    """Control 节点的控制语义，对应设计书附件一表7。"""

    START = "start"
    END = "end"
    IF = "if"
    LOOP = "loop"
    PARALLEL = "parallel"
    CONSENSUS = "consensus"


class ComplexityLevel(str, Enum):
    """ACG 复杂度等级，对应设计书表2.2 ACG 字段结构。"""

    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"
    EXTREME = "extreme"


__all__ = ["NodeType", "EdgeType", "ControlType", "ComplexityLevel"]
