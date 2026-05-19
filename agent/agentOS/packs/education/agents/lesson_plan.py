from agentos.agents.base import AgentOutput, AgentProfile, BaseAgent


def _infer_subject(topic: str, explicit: str) -> str:
    if explicit and explicit.lower() != "general":
        return explicit
    if any(keyword in topic for keyword in ["数学", "函数", "方程", "几何", "代数"]):
        return "数学"
    if any(keyword in topic for keyword in ["英语", "语法", "阅读", "作文"]):
        return "英语"
    if any(keyword in topic for keyword in ["语文", "古诗", "文言文", "写作"]):
        return "语文"
    if any(keyword in topic for keyword in ["物理", "力学", "电路"]):
        return "物理"
    return explicit or "通用学科"


def _infer_grade(topic: str, explicit: str) -> str:
    if explicit and explicit.lower() != "general":
        return explicit
    for grade in ["一年级", "二年级", "三年级", "四年级", "五年级", "六年级", "七年级", "八年级", "九年级", "初一", "初二", "初三", "高一", "高二", "高三"]:
        if grade in topic:
            return grade
    return explicit or "通用年级"


def _build_lesson_markdown(plan: dict) -> str:
    objectives = plan.get("objectives", [])
    activities = plan.get("activities", [])
    assessment = plan.get("assessment", [])
    homework = plan.get("homework", [])
    lines = [
        f"## 教学设计：{plan.get('topic', '课程主题')}",
        "",
        f"- 学科：{plan.get('subject', '通用学科')}",
        f"- 年级：{plan.get('grade', '通用年级')}",
        f"- 课时：{plan.get('duration_minutes', 45)} 分钟",
        "",
        "### 1. 教学目标",
        *[f"- {item}" for item in objectives],
        "",
        "### 2. 教学流程",
    ]
    for item in activities:
        lines.append(f"- {item}")
    lines.extend(["", "### 3. 课堂评价", *[f"- {item}" for item in assessment]])
    lines.extend(["", "### 4. 课后任务", *[f"- {item}" for item in homework]])
    lines.extend(["", "### 5. 边界与提醒", "- 如果学生基础差异较大，建议把例题分为基础、提升两档。", "- 如果课堂时间不足，保留形成性评价，压缩拓展练习。"])
    return "\n".join(lines)


class LessonPlanAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            AgentProfile(
                agentName="lesson_plan",
                domain="education",
                capabilities=["lesson_plan", "teaching_design"],
                allowedSkills=["lesson_plan_generation"],
                description="Creates a minimal lesson plan from teaching task input.",
            )
        )

    async def run(self, context):
        task_input = context.task.input
        topic = str(task_input.get("topic") or context.task.title).strip()
        subject = _infer_subject(topic, str(task_input.get("subject") or "general").strip())
        grade = _infer_grade(topic, str(task_input.get("grade") or "general").strip())
        plan = {
            "topic": topic,
            "subject": subject,
            "grade": grade,
            "duration_minutes": 45,
            "objectives": [
                f"理解并能说明“{topic}”的核心概念与适用场景。",
                "能在教师引导下完成基础例题，并解释关键步骤。",
                "能识别常见错误，并用规范语言总结解题或应用方法。",
            ],
            "activities": [
                "导入诊断（5分钟）：用一个生活化问题快速了解学生已有认知。",
                "概念讲解（10分钟）：用图示、例子或类比建立核心概念。",
                "例题示范（10分钟）：教师完整示范一题，突出思路而不是机械步骤。",
                "分层练习（15分钟）：基础题全员完成，提升题供学有余力学生挑战。",
                "总结反馈（5分钟）：学生说出本节课的一个收获和一个易错点。",
            ],
            "assessment": [
                "观察学生能否独立说出核心概念。",
                "抽查练习过程，判断是否存在步骤跳跃或概念混淆。",
                "用出口题检验本节课最低掌握目标。",
            ],
            "homework": [
                "完成 3 道基础巩固题。",
                "整理 1 个课堂易错点，并写出纠正方法。",
                "选做 1 道拓展题，用于下节课开头交流。",
            ],
        }
        final_answer = _build_lesson_markdown(plan)
        return AgentOutput(
            output={
                "lesson_plan": plan,
                "final_answer": final_answer,
            },
            summary="Chinese lesson plan generated.",
        )
