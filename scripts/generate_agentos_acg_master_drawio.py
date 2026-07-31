"""Generate the editable Draw.io master architecture for Kinlin AgentOS.

The layout deliberately follows the 1600x982 architecture figure embedded in
``claude context/完成稿.docx`` while replacing generic labels with the current
repository's implemented modules and explicitly marked evolution targets.
"""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "docs"
    / "02-架构设计"
    / "figures"
    / "知弈AgentOS_ACG总体架构_完成稿与未来蓝图.drawio"
)

FONT = "Microsoft YaHei"

STATUS = {
    "done": {
        "color": "#009E7A",
        "fill": "#ECF8F5",
        "stroke": "#1AA888",
        "dash": "0",
    },
    "evolving": {
        "color": "#F59E0B",
        "fill": "#FFF7E8",
        "stroke": "#E9A23B",
        "dash": "0",
    },
    "future": {
        "color": "#64748B",
        "fill": "#F8FAFC",
        "stroke": "#94A3B8",
        "dash": "1",
    },
}

LAYER = {
    "L0": {"accent": "#00A896", "fill": "#E7F8F5", "panel": "#F6FCFB", "border": "#46BFB0"},
    "L1": {"accent": "#2563EB", "fill": "#EAF2FF", "panel": "#F7FAFF", "border": "#7AA6F7"},
    "L2": {"accent": "#7C3AED", "fill": "#F2ECFF", "panel": "#FBF9FF", "border": "#B79AF5"},
    "L3": {"accent": "#0891B2", "fill": "#E7F7FA", "panel": "#F6FCFD", "border": "#6DC4D4"},
    "L4": {"accent": "#F43F5E", "fill": "#FFF0F3", "panel": "#FFF8F9", "border": "#F59BAA"},
    "L5": {"accent": "#334155", "fill": "#EEF2F6", "panel": "#F8FAFC", "border": "#A3B2C3"},
}


mxfile = ET.Element(
    "mxfile",
    {
        "host": "Electron",
        "agent": "draw.io/29.3.0",
        "version": "29.3.0",
        "pages": "1",
    },
)
diagram = ET.SubElement(
    mxfile,
    "diagram",
    {"name": "总体架构图", "id": "kinlin-agentos-acg-master"},
)
model = ET.SubElement(
    diagram,
    "mxGraphModel",
    {
        "dx": "1600",
        "dy": "982",
        "grid": "0",
        "gridSize": "10",
        "guides": "1",
        "tooltips": "1",
        "connect": "1",
        "arrows": "1",
        "fold": "1",
        "page": "1",
        "pageScale": "1",
        "pageWidth": "1600",
        "pageHeight": "982",
        "math": "0",
        "shadow": "0",
        "background": "#F6F8FB",
    },
)
root = ET.SubElement(model, "root")
ET.SubElement(root, "mxCell", {"id": "0"})
ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})


def vertex(
    cell_id: str,
    value: str,
    x: float,
    y: float,
    width: float,
    height: float,
    style: str,
    *,
    parent: str = "1",
) -> None:
    cell = ET.SubElement(
        root,
        "mxCell",
        {
            "id": cell_id,
            "value": value,
            "style": style,
            "parent": parent,
            "vertex": "1",
        },
    )
    ET.SubElement(
        cell,
        "mxGeometry",
        {
            "x": str(x),
            "y": str(y),
            "width": str(width),
            "height": str(height),
            "as": "geometry",
        },
    )


def edge(
    cell_id: str,
    source: str,
    target: str,
    *,
    style: str | None = None,
    value: str = "",
    points: list[tuple[float, float]] | None = None,
) -> None:
    if style is None:
        style = (
            "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;"
            "jettySize=auto;html=1;strokeColor=#435466;strokeWidth=1;"
            "endArrow=classic;endFill=1;"
        )
    cell = ET.SubElement(
        root,
        "mxCell",
        {
            "id": cell_id,
            "value": value,
            "style": style,
            "parent": "1",
            "source": source,
            "target": target,
            "edge": "1",
        },
    )
    geometry = ET.SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})
    if points:
        array = ET.SubElement(geometry, "Array", {"as": "points"})
        for px, py in points:
            ET.SubElement(array, "mxPoint", {"x": str(px), "y": str(py)})


def html_text(title: str, subtitle: str = "", status: str | None = None) -> str:
    prefix = ""
    if status:
        marker = "◇" if status == "future" else "●"
        prefix = f'<font color="{STATUS[status]["color"]}">{marker}</font> '
    if subtitle:
        return (
            f'{prefix}<b>{title}</b><br>'
            f'<font color="#596776">{subtitle}</font>'
        )
    return f"{prefix}<b>{title}</b>"


def card_style(
    status: str = "done",
    *,
    font_size: int = 12,
    align: str = "center",
    vertical: str = "middle",
    spacing_left: int = 5,
    arc: int = 10,
) -> str:
    spec = STATUS[status]
    dash = "dashed=1;dashPattern=5 4;" if spec["dash"] == "1" else ""
    return (
        "rounded=1;whiteSpace=wrap;html=1;"
        f'fillColor={spec["fill"]};strokeColor={spec["stroke"]};'
        f"strokeWidth=1;arcSize={arc};{dash}"
        f"fontFamily={FONT};fontSize={font_size};fontColor=#172B2E;"
        f"align={align};verticalAlign={vertical};spacingLeft={spacing_left};"
        "spacingRight=5;spacingTop=3;spacingBottom=3;"
    )


TEXT = (
    "text;html=1;strokeColor=none;fillColor=none;whiteSpace=wrap;"
    f"fontFamily={FONT};fontColor=#172B2E;verticalAlign=middle;"
)
CONTAINER = (
    "rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;"
    "strokeColor=#A9B4C0;strokeWidth=1;arcSize=5;"
)
GROUP = (
    "rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;"
    "strokeColor=#A7B3BF;strokeWidth=1;"
    f"fontFamily={FONT};fontColor=#172B2E;verticalAlign=top;spacingTop=5;arcSize=6;"
)
BUS = (
    "rounded=1;whiteSpace=wrap;html=1;fillColor=#E6F9FB;"
    "strokeColor=#22A8B5;strokeWidth=1;arcSize=8;"
    f"fontFamily={FONT};fontColor=#0E6670;fontSize=11;fontStyle=1;"
)
EDGE_DOWN = (
    "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;strokeColor=#435466;"
    "strokeWidth=1.1;endArrow=classic;endFill=1;"
    "exitX=0.5;exitY=1;entryX=0.5;entryY=0;"
)
EDGE_DASH = (
    "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;strokeColor=#708090;"
    "strokeWidth=1;dashed=1;dashPattern=5 4;endArrow=classic;endFill=1;"
)


def layer_label(cell_id: str, level: str, cn: str, en: str, y: int, height: int) -> None:
    palette = LAYER[level]
    value = (
        f'<b>{level} {cn}</b><br>'
        f'<font color="{palette["accent"]}" style="font-size: 12px">{en}</font>'
    )
    vertex(
        cell_id,
        value,
        10,
        y,
        132,
        height,
        f'rounded=1;whiteSpace=wrap;html=1;fillColor={palette["fill"]};'
        f'strokeColor={palette["border"]};strokeWidth=1.2;arcSize=8;'
        f'fontFamily={FONT};fontColor={palette["accent"]};fontSize=14;align=center;'
        "verticalAlign=middle;spacing=4;",
    )


def layer_title(cell_id: str, value: str, x: int, y: int, width: int, level: str) -> None:
    vertex(
        cell_id,
        f"<b>{value}</b>",
        x,
        y,
        width,
        22,
        TEXT + f'fontSize=16;fontStyle=1;align=center;fontColor={LAYER[level]["accent"]};',
    )


def layer_panel_style(level: str) -> str:
    palette = LAYER[level]
    return (
        "rounded=1;whiteSpace=wrap;html=1;"
        f'fillColor={palette["panel"]};strokeColor={palette["border"]};'
        "strokeWidth=1.1;arcSize=5;"
    )


# ---------------------------------------------------------------------------
# Page furniture and status legend
# ---------------------------------------------------------------------------
vertex(
    "canvas_bg",
    "",
    0,
    0,
    1600,
    982,
    "rounded=0;whiteSpace=wrap;html=1;fillColor=#F6F8FB;strokeColor=none;locked=1;",
)
vertex(
    "title",
    "<b>知弈 AgentOS · 动态异构群体智能架构（ACG）总体架构图</b>",
    250,
    1,
    1100,
    32,
    TEXT + "fontSize=25;fontStyle=1;align=center;fontColor=#0B3B3A;",
)
vertex(
    "scope_note",
    "完成稿复刻 · V1.0-alpha 真实能力与未来蓝图统一视图",
    12,
    34,
    520,
    18,
    TEXT + "fontSize=10;align=left;fontColor=#64748B;",
)
legend_value = (
    '<font color="#009E7A">●</font> 已实现　'
    '<font color="#F59E0B">●</font> 演进中　'
    '<font color="#64748B">◇</font> 未来蓝图（虚线框）'
)
vertex(
    "status_legend",
    legend_value,
    1050,
    34,
    538,
    18,
    TEXT + "fontSize=10;align=right;fontColor=#475467;",
)


# ---------------------------------------------------------------------------
# Layer labels and structural containers
# ---------------------------------------------------------------------------
layer_label("label_l0", "L0", "目标与契约层", "Goal & Contract Layer", 53, 73)
layer_label("label_l1", "L1", "认知规划层", "Cognitive Planning Layer", 151, 146)
layer_label("label_l2", "L2", "群体组织层", "Swarm Organization Layer", 339, 101)
layer_label("label_l3", "L3", "执行与治理层", "Execution & Governance", 476, 127)
layer_label("label_l4", "L4", "自愈恢复层", "Self-Healing Layer", 682, 93)
layer_label("label_l5", "L5", "基础设施层", "Infrastructure Layer", 806, 112)

vertex("l1_box", "", 163, 151, 1297, 165, layer_panel_style("L1"))
vertex("l2_box", "", 163, 335, 1297, 116, layer_panel_style("L2"))
vertex("l3_box", "", 163, 470, 1297, 213, layer_panel_style("L3"))
vertex("l4_box", "", 163, 695, 1297, 106, layer_panel_style("L4"))
vertex("l5_box", "", 151, 811, 1437, 155, layer_panel_style("L5"))
vertex(
    "right_rail",
    "",
    1482,
    153,
    106,
    634,
    "rounded=1;whiteSpace=wrap;html=1;fillColor=#F8FAFC;strokeColor=#9AA8B7;strokeWidth=1.1;arcSize=5;",
)

layer_title("l1_title", "认知规划引擎（Cognitive Planning Engine）", 163, 156, 855, "L1")
layer_title("l2_title", "群体组织层（动态能力编组与受控协作）", 163, 339, 1297, "L2")
layer_title("l3_title", "执行与治理运行时（Workflow Runtime）", 163, 473, 1297, "L3")
layer_title("l4_title", "自愈恢复控制器（Self-Healing Controller）", 163, 699, 1297, "L4")
layer_title("l5_title", "基础设施与资源织网（跨层支撑能力）", 151, 812, 1437, "L5")


# Cross-layer flow; short connectors occupy the gaps between layer bands.
edge("down_0_1", "l0_environment", "l1_box", style=EDGE_DOWN)
edge("down_1_2", "l1_box", "l2_box", style=EDGE_DOWN)
edge("down_2_3", "l2_box", "l3_box", style=EDGE_DOWN)
edge("down_3_4", "l3_event_bus", "l4_box", style=EDGE_DOWN)


# ---------------------------------------------------------------------------
# L0 — goal, task contract, environmental context and feedback
# ---------------------------------------------------------------------------
vertex(
    "l0_user",
    html_text("用户意图与任务输入", "职业工作台 · 自然语言 · 合同文本", "done"),
    217,
    53,
    251,
    73,
    card_style("done", font_size=13),
)
vertex("l0_mid", "", 529, 55, 645, 72, CONTAINER)
vertex(
    "l0_contract",
    html_text("Task Manager / Contract", "Task 对象 · 风险 · 预算 · 权限 · Review", "done"),
    540,
    62,
    190,
    58,
    TEXT + "fontSize=12;align=center;",
)
vertex(
    "l0_environment",
    html_text("环境与证据", "Agent · Skill · Tool · Model<br>keyword Evidence（演示）", "evolving"),
    755,
    62,
    195,
    58,
    TEXT + "fontSize=12;align=center;",
)
vertex(
    "l0_feedback",
    html_text("反馈与治理", "Review · Metrics · User Feedback", "done"),
    975,
    62,
    188,
    58,
    TEXT + "fontSize=12;align=center;",
)
vertex(
    "l0_goal",
    html_text("高层交付目标", "可治理 · 可追溯 · 受控故障可恢复", "done"),
    1243,
    56,
    217,
    70,
    card_style("done", font_size=13),
)
edge("l0_e1", "l0_user", "l0_contract")
edge("l0_e2", "l0_contract", "l0_environment")
edge("l0_e3", "l0_environment", "l0_feedback")
edge("l0_e4", "l0_feedback", "l0_goal")


# ---------------------------------------------------------------------------
# L1 — cognitive planning and ACG blueprint
# ---------------------------------------------------------------------------
planning_cards = [
    ("plan_intent", 178, 124, "IntentParser", "意图解析 · 语义画像", "done"),
    ("plan_task", 322, 122, "TaskSemanticProfile", "目标 · 约束 · 复杂度 · 熵预算", "done"),
    ("plan_template", 464, 130, "TemplateMatcher", "静态优选 · 线性升格", "done"),
    ("plan_router", 614, 122, "CognitiveRouter", "能力路由 · 效用评分", "evolving"),
    ("plan_role", 752, 121, "Role / Skill Matcher", "角色绑定 · 能力画像", "evolving"),
    ("plan_builder", 891, 118, "ACGBuilder", "构建/校验 · 线性升格", "done"),
]
for cell_id, x, width, title, subtitle, status in planning_cards:
    vertex(
        cell_id,
        html_text(title, subtitle, status),
        x,
        187,
        width,
        94,
        card_style(status, font_size=11),
    )

for idx, (source, target) in enumerate(
    zip([c[0] for c in planning_cards], [c[0] for c in planning_cards][1:]), 1
):
    edge(f"plan_edge_{idx}", source, target)

vertex(
    "plan_strategy",
    '<b>静态优选</b>：模板命中 → promote_workflow_to_acg　｜　'
    '<b>动态补位</b>：能力路由 → ACG 构建　｜　'
    '<font color="#64748B">◇ 自动发现复杂并行子图</font>',
    178,
    286,
    831,
    23,
    TEXT + "fontSize=9;align=center;fontColor=#52606D;",
)

vertex(
    "acg_preview",
    "",
    1018,
    163,
    326,
    147,
    "rounded=1;whiteSpace=wrap;html=1;fillColor=#F8FBFF;"
    "strokeColor=#2563EB;strokeWidth=1.2;arcSize=7;",
)
vertex(
    "acg_preview_title",
    "<b>ACG 运行拓扑（示例）</b>",
    1090,
    156,
    185,
    20,
    TEXT + "fontSize=12;align=center;fillColor=#FFFFFF;fontColor=#2563EB;",
)
edge("plan_to_acg", "plan_builder", "acg_preview")

# Mini graph: 6 node types, intentionally colorful like the reference figure.
graph_nodes = [
    ("g_a1", "A", 1040, 187, "ellipse;fillColor=#BDD0FC;strokeColor=#2563EB;"),
    ("g_s1", "S", 1035, 230, "rounded=0;fillColor=#F8C84E;strokeColor=#F97316;"),
    ("g_m1", "M", 1068, 260, "shape=cylinder3;fillColor=#B9E8EF;strokeColor=#0891B2;"),
    ("g_k1", "K", 1072, 210, "shape=hexagon;fillColor=#B2D8A8;strokeColor=#16803A;"),
    ("g_s2", "S", 1100, 260, "rounded=0;fillColor=#F8C84E;strokeColor=#F97316;"),
    ("g_e1", "E", 1125, 218, "shape=document;fillColor=#E7D8F5;strokeColor=#7C3AED;"),
    ("g_c1", "C", 1162, 240, "shape=rhombus;fillColor=#FCC2BE;strokeColor=#EF4444;"),
    ("g_a2", "A", 1177, 181, "ellipse;fillColor=#BDD0FC;strokeColor=#2563EB;"),
    ("g_s3", "S", 1210, 215, "rounded=0;fillColor=#F8C84E;strokeColor=#F97316;"),
    ("g_m2", "M", 1238, 252, "shape=cylinder3;fillColor=#B9E8EF;strokeColor=#0891B2;"),
    ("g_e2", "E", 1262, 208, "shape=document;fillColor=#E7D8F5;strokeColor=#7C3AED;"),
    ("g_a3", "A", 1291, 182, "ellipse;fillColor=#BDD0FC;strokeColor=#2563EB;"),
    ("g_c2", "C", 1301, 250, "shape=rhombus;fillColor=#FCC2BE;strokeColor=#EF4444;"),
]
for cell_id, label, x, y, shape_style in graph_nodes:
    vertex(
        cell_id,
        f"<b>{label}</b>",
        x,
        y,
        20,
        20,
        shape_style
        + "whiteSpace=wrap;html=1;strokeWidth=1;"
        + f"fontFamily={FONT};fontSize=8;align=center;verticalAlign=middle;",
    )

mini_edge = (
    "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;strokeColor=#64748B;"
    "strokeWidth=0.8;endArrow=block;endFill=1;endSize=4;"
)
for idx, (source, target) in enumerate(
    [
        ("g_a1", "g_k1"),
        ("g_a1", "g_s1"),
        ("g_s1", "g_m1"),
        ("g_k1", "g_e1"),
        ("g_m1", "g_s2"),
        ("g_s2", "g_c1"),
        ("g_e1", "g_c1"),
        ("g_a2", "g_c1"),
        ("g_a2", "g_s3"),
        ("g_c1", "g_s3"),
        ("g_s3", "g_m2"),
        ("g_s3", "g_e2"),
        ("g_e2", "g_a3"),
        ("g_m2", "g_c2"),
        ("g_a3", "g_c2"),
    ],
    1,
):
    edge(f"mini_edge_{idx}", source, target, style=mini_edge)

vertex(
    "acg_legend",
    "",
    1346,
    157,
    104,
    151,
    "rounded=1;whiteSpace=wrap;html=1;fillColor=#FBF9FF;strokeColor=#8B5CF6;strokeWidth=1.1;arcSize=7;",
)
legend_rows = [
    ("#2563EB", "Agent"),
    ("#F97316", "Step"),
    ("#16803A", "Skill"),
    ("#7C3AED", "Evidence"),
    ("#0891B2", "Memory"),
    ("#EF4444", "Control"),
]
for idx, (color, label) in enumerate(legend_rows):
    vertex(
        f"acg_legend_{idx}",
        f'<font color="{color}">●</font> {label}',
        1354,
        166 + idx * 22,
        88,
        18,
        TEXT + "fontSize=9;align=left;",
    )
vertex(
    "acg_legend_note",
    "6 类节点 · 7 类边",
    1354,
    296,
    88,
    9,
    TEXT + "fontSize=7;align=center;fontColor=#64748B;",
)


# ---------------------------------------------------------------------------
# L2 — capability registry, team formation, collaboration and governance
# ---------------------------------------------------------------------------
l2_cards = [
    ("org_registry", 182, 195, "Agent / Skill Registry", "能力注册 · 生命周期 · 画像", "done"),
    ("org_pack", 405, 183, "Pack 能力发现", "legal · education<br>programmer · writer", "done"),
    ("org_team", 616, 192, "角色绑定与团队构建", "Step ↔ Agent ↔ Skill", "evolving"),
    ("org_contract", 836, 182, "协作拓扑与通信契约", "input_spec · ContextPack<br>熵预算", "evolving"),
    ("org_consensus", 1046, 182, "共识与冲突控制", "投票 · 辩论 · 冲突消解", "future"),
    ("org_policy", 1256, 182, "Policy / Human Review", "风险门控<br>approve · rerun · reject", "done"),
]
for cell_id, x, width, title, subtitle, status in l2_cards:
    vertex(
        cell_id,
        html_text(title, subtitle, status),
        x,
        366,
        width,
        70,
        card_style(status, font_size=11),
    )

edge(
    "org_feedback",
    "org_policy",
    "plan_router",
    style=EDGE_DASH
    + "exitX=0.5;exitY=0;entryX=0.5;entryY=1;",
    value="◇ 运行信号闭环",
    points=[(1340, 326), (675, 326)],
)


# ---------------------------------------------------------------------------
# L3 — scheduler, adapter router, executor pool and governance plane
# ---------------------------------------------------------------------------
vertex("sched_group", "<b>调度逻辑（Scheduler）</b>", 176, 495, 216, 160, GROUP + "fontSize=11;align=center;")
vertex("dispatch_group", "<b>分发器（Dispatcher）</b>", 407, 495, 200, 160, GROUP + "fontSize=11;align=center;")
vertex("executor_group", "<b>执行器池（Executor Pool）</b>", 619, 504, 545, 134, CONTAINER + f"fontFamily={FONT};fontSize=11;fontStyle=1;verticalAlign=top;spacingTop=5;align=center;")
vertex("audit_group", "<b>治理平面（Governance Plane）</b>", 1176, 495, 238, 160, GROUP + "fontSize=11;align=center;")

scheduler_cards = [
    ("sched_ready", 518, "就绪集调度", "依赖满足 · 并行批次", "done"),
    ("sched_priority", 558, "并发批次控制", "ready-set 批次 · 并发上限", "done"),
    ("sched_resource", 598, "优先级 / 资源优化", "Task 排序 · 负载 · 成本 · 端边云", "future"),
]
for cell_id, y, title, subtitle, status in scheduler_cards:
    vertex(cell_id, html_text(title, subtitle, status), 185, y, 198, 36, card_style(status, font_size=9))

dispatcher_cards = [
    ("dispatch_adapter", 522, "Execution Adapter", "acg / external", "done"),
    ("dispatch_agent", 579, "Agent / Skill 分派", "能力匹配 · Orchestrator", "done"),
]
for cell_id, y, title, subtitle, status in dispatcher_cards:
    vertex(cell_id, html_text(title, subtitle, status), 417, y, 180, 50, card_style(status, font_size=10))

executor_cards = [
    ("exec_acg", 635, "ACGExecutor", "ready_steps<br>async gather", "done"),
    ("exec_governance", 867, "治理闭环", "Trace / Review<br>Checkpoint", "done"),
    ("exec_io", 983, "Agent / Tool / RAG", "LLM Gateway<br>Evidence / Data", "done"),
]
for cell_id, x, title, subtitle, status in executor_cards:
    vertex(cell_id, html_text(title, subtitle, status), x, 531, 104, 88, card_style(status, font_size=10))

audit_cards = [
    ("audit_trace", 518, "Trace / Provenance", "步骤事件 · 数据血缘", "done"),
    ("audit_review", 558, "Checkpoint / Review", "快照 · 人工审核", "done"),
    ("audit_eval", 598, "Evaluation / Policy", "治理指标 · 合规策略", "evolving"),
]
for cell_id, y, title, subtitle, status in audit_cards:
    vertex(cell_id, html_text(title, subtitle, status), 1188, y, 214, 36, card_style(status, font_size=9))

edge("exec_chain_1", "sched_group", "dispatch_group")
edge("exec_chain_2", "dispatch_group", "executor_group")
edge("exec_chain_3", "executor_group", "audit_group")

vertex(
    "l3_event_bus",
    '<font color="#F59E0B">●</font> <b>低熵上下文总线</b>（Low-Entropy Context Bus）　'
    'ContextAssembler · ContextPack · input_spec · ProvenanceLedger　'
    '<font color="#64748B">◇ 动态摘要压缩</font>',
    407,
    655,
    1007,
    25,
    BUS,
)
for idx, source in enumerate(["dispatch_group", "executor_group", "audit_group"], 1):
    edge(
        f"bus_link_{idx}",
        source,
        "l3_event_bus",
        style=(
            "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;strokeColor=#708090;"
            "strokeWidth=0.9;endArrow=none;startArrow=none;"
            "exitX=0.5;exitY=1;entryX=0.5;entryY=0;"
        ),
    )


# ---------------------------------------------------------------------------
# L4 — recoverable-fault loop and future replacement mechanisms
# ---------------------------------------------------------------------------
l4_cards = [
    ("heal_fault", 177, 190, "故障检测 / 注入", "timeout · crash · empty evidence", "done"),
    ("heal_checkpoint", 416, 165, "Checkpoint", "状态快照 · 可恢复点", "done"),
    ("heal_restore", 627, 151, "上下文恢复", "步骤状态 · 输出 · 证据", "done"),
    ("heal_replan", 827, 158, "local_replan / retry", "受影响子图复位重跑", "done"),
    ("heal_replace", 1033, 155, "Agent / 模型 / 资源替换", "备用接管 · Resource 重选", "future"),
    ("heal_resume", 1234, 189, "恢复调度与审计", "续跑 · recoveryTrace · Trace", "done"),
]
for cell_id, x, width, title, subtitle, status in l4_cards:
    vertex(
        cell_id,
        html_text(title, subtitle, status),
        x,
        722,
        width,
        68,
        card_style(status, font_size=10),
    )

heal_current = ["heal_fault", "heal_checkpoint", "heal_restore", "heal_replan"]
for idx, (source, target) in enumerate(zip(heal_current, heal_current[1:]), 1):
    edge(f"heal_current_{idx}", source, target)
edge(
    "heal_current_resume",
    "heal_replan",
    "heal_resume",
    style=(
        "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;strokeColor=#435466;"
        "strokeWidth=1;endArrow=classic;endFill=1;"
        "exitX=1;exitY=0.78;entryX=0;entryY=0.78;"
    ),
    points=[(1008, 796), (1210, 796)],
)
edge("heal_future_1", "heal_replan", "heal_replace", style=EDGE_DASH)
edge("heal_future_2", "heal_replace", "heal_resume", style=EDGE_DASH)

edge(
    "heal_loop",
    "heal_resume",
    "audit_group",
    style=(
        "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;strokeColor=#64748B;"
        "strokeWidth=1;endArrow=classic;endFill=1;"
        "exitX=0.5;exitY=0;entryX=0.5;entryY=1;"
    ),
    points=[(1328, 690), (1295, 690)],
)


# ---------------------------------------------------------------------------
# L5 — memory, communication, resource and observability fabrics
# ---------------------------------------------------------------------------
infra_groups = [
    ("memory_group", 160, 344, "记忆中枢（Memory Fabric）", "#00A896"),
    ("communication_group", 519, 314, "通信总线（Communication Fabric）", "#2563EB"),
    ("resource_group", 846, 348, "资源池（Resource & Model Pool）", "#F59E0B"),
    ("observability_group", 1208, 368, "可观测与安全（Observability & Security）", "#8B5CF6"),
]
for cell_id, x, width, title, accent in infra_groups:
    vertex(
        cell_id,
        f"<b>{title}</b>",
        x,
        834,
        width,
        122,
        f"rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor={accent};"
        f"strokeWidth=1.15;arcSize=6;fontFamily={FONT};fontSize=10;fontColor={accent};"
        "fontStyle=1;align=center;verticalAlign=top;spacingTop=4;",
    )

memory_items = [
    ("mem_work", 168, 78, "Workflow<br>State Store", "done"),
    ("mem_evidence", 251, 78, "Evidence<br>Store", "done"),
    ("mem_semantic", 334, 78, "Semantic /<br>Federated", "future"),
    ("mem_checkpoint", 417, 78, "Checkpoint<br>Memory", "evolving"),
]
for cell_id, x, width, label, status in memory_items:
    vertex(cell_id, html_text(label, "", status), x, 858, width, 55, card_style(status, font_size=9))
vertex(
    "memory_footer",
    'Memory / SQLite　｜　PostgreSQL / Redis　｜　<font color="#64748B">◇ Vector / Capsule</font>',
    168,
    921,
    328,
    28,
    BUS + "fontSize=8;",
)

communication_items = [
    ("comm_pack", 527, 70, "ContextPack", "done"),
    ("comm_prov", 603, 70, "Provenance", "done"),
    ("comm_entropy", 679, 70, "Entropy<br>Budget", "evolving"),
    ("comm_compress", 755, 70, "压缩 / 唤醒", "future"),
]
for cell_id, x, width, label, status in communication_items:
    vertex(cell_id, html_text(label, "", status), x, 858, width, 55, card_style(status, font_size=8))
vertex(
    "communication_footer",
    'input_spec ｜ Structured Message ｜ <font color="#64748B">◇ Context Compression</font>',
    527,
    921,
    298,
    28,
    BUS + "fontSize=8;",
)

resource_items = [
    ("res_llm", 854, 79, "LLM<br>Gateway", "done"),
    ("res_tools", 939, 79, "Tool / keyword<br>Retriever", "done"),
    ("res_adapters", 1024, 79, "Execution<br>Adapters", "done"),
    ("res_fabric", 1109, 77, "端 · 边 · 云<br>Resource", "future"),
]
for cell_id, x, width, label, status in resource_items:
    vertex(cell_id, html_text(label, "", status), x, 858, width, 55, card_style(status, font_size=8))
vertex(
    "resource_footer",
    'DeepSeek / Qwen / Mock　｜　Tool / Evidence　｜　<font color="#64748B">◇ Resource Fabric</font>',
    854,
    921,
    332,
    28,
    BUS + "fontSize=8;",
)

observability_items = [
    ("obs_trace", 1216, 82, "Trace /<br>Metrics", "done"),
    ("obs_logs", 1304, 82, "Logs /<br>Alerts", "evolving"),
    ("obs_review", 1392, 82, "Review /<br>Audit", "done"),
    ("obs_security", 1480, 88, "租户 / 脱敏<br>合规策略", "future"),
]
for cell_id, x, width, label, status in observability_items:
    vertex(cell_id, html_text(label, "", status), x, 858, width, 55, card_style(status, font_size=8))
vertex(
    "observability_footer",
    '可视化看板 ｜ 成本/质量 ｜ JWT / Policy ｜ <font color="#64748B">◇ Multi-tenant</font>',
    1216,
    921,
    352,
    28,
    BUS + "fontSize=8;",
)


# ---------------------------------------------------------------------------
# Right-side delivery and traceability rail
# ---------------------------------------------------------------------------
vertex(
    "delivery_title",
    "<b>最终交付物</b><br><font color=\"#64748B\">Deliverables</font>",
    1488,
    160,
    94,
    38,
    TEXT + "fontSize=11;align=center;fontColor=#F97316;",
)
delivery_cards = [
    ("delivery_risk", 202, "风险项 / Evidence", "done"),
    ("delivery_advice", 246, "修改建议 / 决策", "done"),
    ("delivery_report", 290, "Markdown 报告", "done"),
    ("delivery_acg", 334, "ACG 拓扑 / 指标", "done"),
    ("delivery_review", 378, "Review / Checkpoint", "done"),
    ("delivery_doc", 422, "Word / PDF 报告", "future"),
]
for cell_id, y, label, status in delivery_cards:
    vertex(cell_id, html_text(label, "", status), 1490, y, 90, 38, card_style(status, font_size=8))

vertex(
    "trace_title",
    "<b>全链路可追溯</b><br><font color=\"#64748B\">Traceability</font>",
    1488,
    475,
    94,
    38,
    TEXT + "fontSize=10;align=center;fontColor=#2563EB;",
)
trace_cards = [
    ("trace_intent", 520, "Task / Intent"),
    ("trace_blueprint", 565, "Blueprint / Route"),
    ("trace_lineage", 610, "Trace / Provenance"),
    ("trace_recovery", 655, "Recovery / Review"),
    ("trace_audit", 700, "Evidence / Audit"),
]
for cell_id, y, label in trace_cards:
    vertex(cell_id, html_text(label, "", "done"), 1490, y, 90, 38, card_style("done", font_size=8))

edge(
    "to_deliverables",
    "l3_box",
    "delivery_report",
    style=(
        "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;strokeColor=#435466;"
        "strokeWidth=1;endArrow=classic;endFill=1;exitX=1;exitY=0.25;entryX=0;entryY=0.5;"
    ),
)
edge(
    "governance_to_trace",
    "audit_group",
    "trace_lineage",
    style=(
        "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;strokeColor=#64748B;"
        "strokeWidth=1;startArrow=classic;startFill=1;endArrow=classic;endFill=1;"
        "exitX=1;exitY=0.5;entryX=0;entryY=0.5;"
    ),
)
edge(
    "trace_to_heal",
    "trace_recovery",
    "heal_resume",
    style=(
        "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;strokeColor=#64748B;"
        "strokeWidth=1;endArrow=classic;endFill=1;"
        "exitX=0;exitY=0.5;entryX=1;entryY=0.5;"
    ),
)


# Small honesty note within the page boundary.
vertex(
    "footer_note",
    "边界口径：当前为 V1.0-alpha 演示闭环；Resource Fabric、分布式/联邦记忆、认知进化、正式法律库/Citation、生产级多租户与 Word/PDF 为未来蓝图。",
    160,
    968,
    1418,
    10,
    TEXT + "fontSize=8;align=center;fontColor=#64748B;",
)


ET.indent(mxfile, space="  ")
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(ET.tostring(mxfile, encoding="unicode") + "\n", encoding="utf-8")
print(OUTPUT)
