import re
from typing import Any, Dict, List, Optional

from app.agent_core.schema.agent_types import PlannedAction


class ReactPlanner:
    """Intent-aware ReAct planner for multi-role agent workflows."""

    def __init__(self, max_plan_steps: int = 10):
        self.max_plan_steps = max_plan_steps

    def _contains_any(self, text: str, tokens: List[str]) -> bool:
        raw = text or ""
        lowered = raw.lower()
        return any(token in raw for token in tokens) or any(token in lowered for token in tokens)

    def _slice_plan(self, actions: List[PlannedAction]) -> List[PlannedAction]:
        return actions[: self.max_plan_steps]

    def _infer_subject(self, text: str) -> str:
        if self._contains_any(text, ["math", "mathematics", "数学", "代数", "几何", "勾股"]):
            return "junior_math"
        if self._contains_any(text, ["physics", "物理", "力学", "电学", "压强", "运动"]):
            return "junior_physics"
        return "general"

    def _infer_grade(self, text: str) -> str:
        lowered = (text or "").lower()
        if "初一" in text or "七年级" in text or "grade 7" in lowered:
            return "grade_7"
        if "初二" in text or "八年级" in text or "grade 8" in lowered:
            return "grade_8"
        if "初三" in text or "九年级" in text or "grade 9" in lowered:
            return "grade_9"
        return "unknown"

    def _latest_user_text(self, history: List[Dict[str, str]]) -> str:
        for item in reversed(history or []):
            if item.get("role") == "user":
                return item.get("content", "")
        return ""

    def _is_teacher_follow_up(self, text: str, history: List[Dict[str, str]]) -> bool:
        if not (text or "").strip() or not history:
            return False

        follow_up_tokens = [
            "再",
            "继续",
            "补充",
            "优化",
            "改",
            "修改",
            "改成",
            "调整",
            "上一个",
            "刚才",
            "环节",
            "有趣",
            "that part",
            "part",
            "revise",
            "update",
            "refine",
            "make it",
            "improve",
        ]
        short_query = len((text or "").strip()) <= 80
        return short_query and self._contains_any(text, follow_up_tokens)

    def _resolve_teacher_follow_up_action(self, text: str, history: List[Dict[str, str]]) -> Optional[str]:
        probe_text = f"{text}\n{self._latest_user_text(history)}"

        if self._contains_any(probe_text, ["教案", "备课", "导入", "环节", "课堂流程", "lesson plan", "warm-up"]):
            return "lesson_plan_generation"
        if self._contains_any(probe_text, ["互动", "提问", "活动", "分组", "互动设计", "interaction", "activity"]):
            return "classroom_interaction_design"
        if self._contains_any(probe_text, ["批改", "评分", "评语", "作文", "grading", "rubric"]):
            return "homework_grading"
        if self._contains_any(probe_text, ["错题", "推题", "变式", "归因", "error analysis", "similar questions"]):
            return "error_analysis_question_push"
        if self._contains_any(probe_text, ["路径", "计划", "周计划", "learning plan", "roadmap"]):
            return "learning_path_planning"
        if self._contains_any(probe_text, ["报告", "学情报告", "report", "progress"]):
            return "progress_report_generation"
        if self._contains_any(probe_text, ["家长", "沟通", "parent", "guardian"]):
            return "parent_communication_suggestion"
        if self._contains_any(probe_text, ["答疑", "讲解", "不会", "question", "how to solve"]):
            return "tutoring_qa"
        return None

    def _extract_positive_int(self, text: str, default: int = 0) -> int:
        raw = text or ""
        cn_match = re.search(r"\u7b2c\s*(\d{1,2})\s*\u7ae0", raw, flags=re.IGNORECASE)
        if cn_match:
            return max(1, int(cn_match.group(1)))

        en_match = re.search(r"(?:chapter|chap(?:ter)?\.?)\s*(\d{1,2})", raw, flags=re.IGNORECASE)
        if en_match:
            return max(1, int(en_match.group(1)))

        direct_match = re.search(r"\b(\d{1,2})\b", raw)
        if direct_match:
            return max(1, int(direct_match.group(1)))
        return default

    def _is_writer_follow_up(self, text: str, history: List[Dict[str, str]]) -> bool:
        if not (text or "").strip() or not history:
            return False
        follow_up_tokens = [
            "\u7ee7\u7eed",
            "\u8865\u5145",
            "\u7eed\u5199",
            "\u4f18\u5316",
            "\u4fee\u6539",
            "continue",
            "revise",
            "rewrite",
            "refine",
            "expand",
        ]
        short_query = len((text or "").strip()) <= 120
        return short_query and self._contains_any(text, follow_up_tokens)

    def _resolve_writer_follow_up_action(self, text: str, history: List[Dict[str, str]]) -> Optional[str]:
        probe_text = f"{text}\n{self._latest_user_text(history)}"
        if self._contains_any(
            probe_text,
            [
                "\u4eba\u7269\u5173\u7cfb",
                "\u5173\u7cfb\u56fe",
                "relation graph",
                "relationship map",
            ],
        ):
            return "character_relation_map"
        if self._contains_any(
            probe_text,
            [
                "\u7075\u611f",
                "\u521b\u610f\u6811",
                "\u601d\u7ef4\u5bfc\u56fe",
                "inspiration",
                "idea tree",
                "mind map",
            ],
        ):
            return "inspiration_expand"
        if self._contains_any(
            probe_text,
            [
                "\u5927\u7eb2",
                "\u7ae0\u8282",
                "outline",
                "chapter plan",
            ],
        ):
            return "outline_generate"
        if self._contains_any(
            probe_text,
            [
                "\u6b63\u6587",
                "\u5199\u4e00\u7ae0",
                "\u7eed\u5199",
                "write chapter",
                "draft chapter",
            ],
        ):
            return "content_write"
        return None

    def _plan_writer(self, state: Dict[str, Any]) -> List[PlannedAction]:
        text = str(state.get("text", "") or "")
        history = state.get("history", []) or []

        actions: List[PlannedAction] = []
        added = set()
        follow_up = self._is_writer_follow_up(text=text, history=history)

        def add_action(thought: str, action: str, action_input: Dict[str, object]) -> None:
            if action in added:
                return
            added.add(action)
            actions.append(
                PlannedAction(
                    thought=thought,
                    action=action,
                    actionInput=action_input,
                )
            )

        chapter_index = self._extract_positive_int(text, default=1)
        chapters_count = max(4, min(20, self._extract_positive_int(text, default=8)))

        if follow_up:
            target_action = self._resolve_writer_follow_up_action(text=text, history=history)
            if target_action:
                action_input: Dict[str, object] = {"followUp": True, "query": text}
                if target_action == "outline_generate":
                    action_input["chapters_count"] = chapters_count
                if target_action == "content_write":
                    action_input["chapter_index"] = chapter_index
                    action_input["style"] = "follow user style"
                add_action(
                    thought="Follow-up writing request detected. Execute only the targeted writer skill.",
                    action=target_action,
                    action_input=action_input,
                )
                return self._slice_plan(actions)

        needs_relation = self._contains_any(
            text,
            [
                "\u4eba\u7269\u5173\u7cfb",
                "\u5173\u7cfb\u56fe",
                "\u89d2\u8272\u5173\u7cfb",
                "relation graph",
                "relationship map",
            ],
        )
        needs_inspiration = self._contains_any(
            text,
            [
                "\u7075\u611f",
                "\u521b\u610f",
                "\u53d1\u6563",
                "\u601d\u7ef4\u5bfc\u56fe",
                "inspiration",
                "idea tree",
                "brainstorm",
            ],
        )
        needs_outline = self._contains_any(
            text,
            [
                "\u5927\u7eb2",
                "\u7ae0\u8282",
                "outline",
                "chapter plan",
            ],
        )
        needs_content = self._contains_any(
            text,
            [
                "\u6b63\u6587",
                "\u7eed\u5199",
                "\u7b2c\u4e00\u7ae0",
                "\u5199\u4e00\u6bb5",
                "\u5199",
                "\u6545\u4e8b",
                "\u521b\u4f5c",
                "\u5c0f\u8bf4",
                "write",
                "draft",
                "chapter",
            ],
        )
        needs_style = self._contains_any(
            text,
            [
                "\u9c81\u8fc5\u4f53",
                "\u98ce\u683c",
                "style",
                "tone",
            ],
        )
        explicit_content_request = self._contains_any(
            text,
            [
                "\u6b63\u6587",
                "\u7eed\u5199",
                "\u7b2c\u4e00\u7ae0",
                "\u5199\u4e00\u6bb5",
                "write chapter",
                "draft chapter",
                "continue writing",
            ],
        )

        relation_only = self._contains_any(
            text,
            [
                "\u4ec5",
                "\u53ea",
                "\u5355\u72ec",
                "only",
                "just",
            ],
        )

        if needs_relation and relation_only and not (needs_inspiration or needs_outline or needs_content):
            add_action(
                thought="User asks for character relationship analysis. Build relation graph directly.",
                action="character_relation_map",
                action_input={"story_description": text},
            )
            return self._slice_plan(actions)

        if needs_inspiration and not (needs_outline or needs_content):
            add_action(
                thought="Expand the premise into multiple creative directions first.",
                action="inspiration_expand",
                action_input={"premise": text},
            )
            return self._slice_plan(actions)

        if needs_outline and not needs_content:
            add_action(
                thought="Generate a chapter-level outline from selected creative direction.",
                action="outline_generate",
                action_input={"creative_selection": text, "chapters_count": chapters_count},
            )
            return self._slice_plan(actions)

        if explicit_content_request and needs_content and not (needs_inspiration or needs_outline or needs_relation):
            add_action(
                thought="Write chapter content directly based on user-provided context.",
                action="content_write",
                action_input={
                    "outline_context": text,
                    "chapter_index": chapter_index,
                    "style": "requested style" if needs_style else "natural narrative",
                },
            )
            return self._slice_plan(actions)

        add_action(
            thought="Start from inspiration expansion to build a structured idea tree.",
            action="inspiration_expand",
            action_input={"premise": text},
        )
        add_action(
            thought="Convert selected ideas into a chapter outline.",
            action="outline_generate",
            action_input={"chapters_count": chapters_count},
        )
        add_action(
            thought="Write chapter content based on outline context and requested style.",
            action="content_write",
            action_input={
                "chapter_index": chapter_index,
                "style": "requested style" if needs_style else "natural narrative",
            },
        )
        if needs_relation:
            add_action(
                thought="Generate a character relation graph for visualization.",
                action="character_relation_map",
                action_input={"story_description": text},
            )
        return self._slice_plan(actions)

    def _is_programmer_follow_up(self, text: str, history: List[Dict[str, str]]) -> bool:
        if not (text or "").strip() or not history:
            return False

        follow_up_tokens = [
            "\u7ee7\u7eed",
            "\u8865\u5145",
            "\u4f18\u5316",
            "\u4fee\u6539",
            "\u8c03\u6574",
            "continue",
            "revise",
            "refine",
            "update",
            "optimize",
        ]
        short_query = len((text or "").strip()) <= 120
        return short_query and self._contains_any(text, follow_up_tokens)

    def _resolve_programmer_follow_up_action(self, text: str, history: List[Dict[str, str]]) -> Optional[str]:
        probe_text = f"{text}\n{self._latest_user_text(history)}"
        if self._contains_any(
            probe_text,
            [
                "\u56fe",
                "\u6d41\u7a0b\u56fe",
                "\u67b6\u6784\u56fe",
                "\u65f6\u5e8f\u56fe",
                "\u7c7b\u56fe",
                "diagram",
                "flowchart",
                "mermaid",
                "sequence",
                "architecture",
            ],
        ):
            return "diagram_generation"
        if self._contains_any(
            probe_text,
            [
                "\u68c0\u7d22",
                "\u4ee3\u7801\u5e93",
                "\u51fd\u6570",
                "\u7c7b",
                "\u5728\u54ea",
                "search",
                "find in code",
                "codebase",
                "semantic search",
            ],
        ):
            return "codebase_semantic_search"
        if self._contains_any(
            probe_text,
            [
                "\u5199\u4ee3\u7801",
                "\u751f\u6210\u4ee3\u7801",
                "\u5b9e\u73b0",
                "\u8865\u4e01",
                "generate code",
                "implement",
                "patch",
                "refactor",
            ],
        ):
            return "code_generation"
        if self._contains_any(
            probe_text,
            [
                "\u9700\u6c42",
                "\u5206\u6790",
                "\u6280\u672f\u65b9\u6848",
                "\u89c4\u683c",
                "requirement",
                "analysis",
                "spec",
                "prd",
            ],
        ):
            return "requirement_analysis"
        return None

    def _infer_diagram_type(self, text: str) -> str:
        if self._contains_any(text, ["\u65f6\u5e8f\u56fe", "sequence", "sequence diagram"]):
            return "sequence"
        if self._contains_any(text, ["\u7c7b\u56fe", "class diagram", "uml class"]):
            return "class"
        if self._contains_any(text, ["\u67b6\u6784\u56fe", "architecture", "system design"]):
            return "architecture"
        return "flowchart"

    def _infer_target_language(self, text: str) -> str:
        lowered = (text or "").lower()
        if self._contains_any(lowered, ["java", "spring"]):
            return "java"
        if self._contains_any(lowered, ["typescript", "ts", "vue", "react", "node"]):
            return "typescript"
        if self._contains_any(lowered, ["javascript", "js"]):
            return "javascript"
        if self._contains_any(lowered, ["go", "golang"]):
            return "go"
        if self._contains_any(lowered, ["rust"]):
            return "rust"
        return "python"

    def _plan_programmer(self, state: Dict[str, Any]) -> List[PlannedAction]:
        text = str(state.get("text", "") or "")
        history = state.get("history", []) or []
        actions: List[PlannedAction] = []
        added = set()
        follow_up = self._is_programmer_follow_up(text=text, history=history)
        diagram_type = self._infer_diagram_type(text)
        target_language = self._infer_target_language(text)

        def add_action(thought: str, action: str, action_input: Dict[str, object]) -> None:
            if action in added:
                return
            added.add(action)
            actions.append(
                PlannedAction(
                    thought=thought,
                    action=action,
                    actionInput=action_input,
                )
            )

        if follow_up:
            target_action = self._resolve_programmer_follow_up_action(text=text, history=history)
            if target_action:
                action_input: Dict[str, object] = {"followUp": True, "query": text}
                if target_action == "codebase_semantic_search":
                    action_input["top_k"] = 5
                if target_action == "code_generation":
                    action_input["target_language"] = target_language
                    action_input["include_diagram"] = self._contains_any(
                        text,
                        ["\u7c7b\u56fe", "\u67b6\u6784\u56fe", "diagram", "mermaid"],
                    )
                if target_action == "diagram_generation":
                    action_input["diagram_type"] = diagram_type
                add_action(
                    thought="Follow-up programming request detected. Execute only the targeted programmer skill.",
                    action=target_action,
                    action_input=action_input,
                )
                return self._slice_plan(actions)

        needs_diagram = self._contains_any(
            text,
            [
                "\u56fe",
                "\u6d41\u7a0b\u56fe",
                "\u67b6\u6784\u56fe",
                "\u65f6\u5e8f\u56fe",
                "\u7c7b\u56fe",
                "diagram",
                "mermaid",
                "flowchart",
                "sequence",
                "architecture",
            ],
        )
        needs_search = self._contains_any(
            text,
            [
                "\u4ee3\u7801\u5e93",
                "\u68c0\u7d22",
                "\u67e5\u627e",
                "\u627e\u51fd\u6570",
                "\u627e\u7c7b",
                "search",
                "find in code",
                "codebase",
                "semantic search",
            ],
        )
        needs_generation = self._contains_any(
            text,
            [
                "\u751f\u6210\u4ee3\u7801",
                "\u5199\u4ee3\u7801",
                "\u5b9e\u73b0",
                "\u4fee\u590d",
                "\u8865\u4e01",
                "generate code",
                "implement",
                "write code",
                "patch",
                "fix",
            ],
        )
        needs_requirement = self._contains_any(
            text,
            [
                "\u9700\u6c42",
                "\u5206\u6790",
                "\u6280\u672f\u89c4\u683c",
                "\u65b9\u6848",
                "requirement",
                "spec",
                "prd",
                "analysis",
            ],
        )
        relation_only = self._contains_any(text, ["\u4ec5", "\u53ea", "\u5355\u72ec", "only", "just"])
        references_project = self._contains_any(
            text,
            [
                "\u8fd9\u4e2a\u9879\u76ee",
                "\u9879\u76ee",
                "\u4ee3\u7801\u5e93",
                "\u5f53\u524d\u5de5\u7a0b",
                "this project",
                "current repo",
                "codebase",
            ],
        )

        if needs_diagram and relation_only and not (needs_search or needs_generation or needs_requirement):
            add_action(
                thought="User asks only for a diagram. Generate Mermaid directly.",
                action="diagram_generation",
                action_input={"query": text, "diagram_type": diagram_type},
            )
            return self._slice_plan(actions)

        if needs_search and not (needs_generation or needs_diagram):
            add_action(
                thought="Retrieve relevant symbols from code index first.",
                action="codebase_semantic_search",
                action_input={"query": text, "top_k": 5},
            )
            return self._slice_plan(actions)

        if needs_requirement and not (needs_generation or needs_diagram or needs_search):
            add_action(
                thought="Convert request into structured technical specification.",
                action="requirement_analysis",
                action_input={"requirement": text},
            )
            return self._slice_plan(actions)

        if needs_diagram and not needs_generation and not needs_requirement:
            if references_project:
                add_action(
                    thought="User references current project. Retrieve code context before diagram generation.",
                    action="codebase_semantic_search",
                    action_input={"query": text, "top_k": 5},
                )
            add_action(
                thought="Generate Mermaid diagram aligned with the request.",
                action="diagram_generation",
                action_input={"query": text, "diagram_type": diagram_type},
            )
            return self._slice_plan(actions)

        if needs_generation and not needs_requirement:
            add_action(
                thought="Retrieve related code context before generating implementation.",
                action="codebase_semantic_search",
                action_input={"query": text, "top_k": 5},
            )
            add_action(
                thought="Generate implementation code using retrieved context.",
                action="code_generation",
                action_input={"target_language": target_language, "include_diagram": needs_diagram},
            )
            if needs_diagram:
                add_action(
                    thought="Generate Mermaid diagram for the implementation flow.",
                    action="diagram_generation",
                    action_input={"query": text, "diagram_type": diagram_type},
                )
            return self._slice_plan(actions)

        add_action(
            thought="Start with requirement analysis to structure implementation scope.",
            action="requirement_analysis",
            action_input={"requirement": text},
        )
        add_action(
            thought="Retrieve relevant code snippets from indexed repository.",
            action="codebase_semantic_search",
            action_input={"query": text, "top_k": 5},
        )
        add_action(
            thought="Generate implementation using specification and code context.",
            action="code_generation",
            action_input={"target_language": target_language, "include_diagram": needs_diagram},
        )
        if needs_diagram or references_project:
            add_action(
                thought="Generate Mermaid diagram for architecture or workflow communication.",
                action="diagram_generation",
                action_input={"query": text, "diagram_type": diagram_type},
            )
        return self._slice_plan(actions)

    def plan(self, text: str, history: List[Dict[str, str]], role: str = "lawyer") -> List[PlannedAction]:
        normalized_role = (role or "lawyer").strip().lower()
        if normalized_role == "teacher":
            return self.plan_teacher(text=text, history=history)
        if normalized_role == "programmer":
            return self._plan_programmer({"text": text, "history": history})
        if normalized_role == "writer":
            return self._plan_writer({"text": text, "history": history})
        return self.plan_lawyer(text=text, history=history)

    def plan_lawyer(self, text: str, history: List[Dict[str, str]]) -> List[PlannedAction]:
        actions: List[PlannedAction] = []
        added = set()

        def add_action(thought: str, action: str, action_input: Dict[str, object]) -> None:
            if action in added:
                return
            added.add(action)
            actions.append(
                PlannedAction(
                    thought=thought,
                    action=action,
                    actionInput=action_input,
                )
            )

        evidence_tokens = ["证据", "微信", "转账", "录音", "证人", "举证", "evidence", "proof"]
        limitation_tokens = ["时效", "过期", "截止", "诉讼时效", "limitation", "deadline"]
        jurisdiction_tokens = ["管辖", "哪个法院", "哪里起诉", "法院", "jurisdiction", "court"]
        hearing_tokens = ["开庭", "庭审", "提纲", "发问", "质证", "辩论", "hearing", "trial"]
        drafting_tokens = ["文书", "起诉状", "答辩状", "律师函", "草稿", "draft", "template"]

        needs_evidence = self._contains_any(text, evidence_tokens)
        needs_limitation = self._contains_any(text, limitation_tokens)
        needs_jurisdiction = self._contains_any(text, jurisdiction_tokens)
        needs_hearing = self._contains_any(text, hearing_tokens)
        needs_document = self._contains_any(text, drafting_tokens)

        add_action(
            thought="Structure the case facts and legal issues first.",
            action="case_understanding",
            action_input={"historySize": len(history)},
        )
        add_action(
            thought="Retrieve relevant statutes for legal grounding.",
            action="statute_retrieval",
            action_input={"query": text, "top_k": 5},
        )
        add_action(
            thought="Retrieve similar cases to support legal reasoning.",
            action="case_retrieval",
            action_input={"query": text, "top_k": 5},
        )

        if needs_evidence or needs_hearing:
            add_action(
                thought="Analyze available evidence and gaps.",
                action="evidence_analysis",
                action_input={"query": text},
            )
        if needs_limitation:
            add_action(
                thought="Calculate limitation period and deadline risks.",
                action="limitation_calculation",
                action_input={"query": text},
            )
        if needs_jurisdiction:
            add_action(
                thought="Determine jurisdiction options and recommendations.",
                action="jurisdiction_determination",
                action_input={"query": text},
            )
        if needs_hearing:
            add_action(
                thought="Generate hearing outline for trial preparation.",
                action="hearing_outline_generation",
                action_input={"outlineType": "trial_preparation"},
            )
        if needs_document:
            add_action(
                thought="Generate requested legal document draft.",
                action="document_generation",
                action_input={"draftType": "general"},
            )

        add_action(
            thought="Finalize with a consolidated risk assessment.",
            action="risk_assessment",
            action_input={"mode": "baseline"},
        )
        return self._slice_plan(actions)

    def plan_teacher(self, text: str, history: List[Dict[str, str]]) -> List[PlannedAction]:
        actions: List[PlannedAction] = []
        added = set()
        subject = self._infer_subject(text)
        grade = self._infer_grade(text)
        follow_up = self._is_teacher_follow_up(text=text, history=history)

        def add_action(thought: str, action: str, action_input: Dict[str, object]) -> None:
            if action in added:
                return
            added.add(action)
            merged_input = {
                "query": text,
                "subject": subject,
                "grade": grade,
                "historySize": len(history),
                **action_input,
            }
            actions.append(
                PlannedAction(
                    thought=thought,
                    action=action,
                    actionInput=merged_input,
                )
            )

        if follow_up:
            target_action = self._resolve_teacher_follow_up_action(text=text, history=history)
            if target_action:
                follow_up_input = {"followUp": True, "mode": "incremental_update"}
                if target_action == "homework_grading":
                    follow_up_input["enableFederated"] = True
                add_action(
                    thought="This is a follow-up refinement, execute only the requested teaching subtask.",
                    action=target_action,
                    action_input=follow_up_input,
                )
                return self._slice_plan(actions)

        needs_diagnosis = self._contains_any(
            text,
            [
                "学情",
                "诊断",
                "薄弱",
                "能力画像",
                "掌握度",
                "student profile",
                "diagnosis",
                "weak points",
            ],
        )
        needs_lesson_plan = self._contains_any(text, ["备课", "教案", "课堂流程", "lesson plan", "teaching plan"])
        needs_grading = self._contains_any(text, ["批改", "评分", "评语", "作文", "homework grading", "rubric"])
        needs_error_push = self._contains_any(text, ["错题", "归因", "推题", "变式", "error analysis", "similar questions"])
        needs_qa = self._contains_any(text, ["答疑", "讲解", "不会", "why", "how", "question", "explain"])
        needs_path = self._contains_any(text, ["学习路径", "学习计划", "周计划", "roadmap", "study plan"])
        needs_report = self._contains_any(text, ["学情报告", "阶段报告", "进步曲线", "report", "progress report"])
        needs_interaction = self._contains_any(text, ["课堂互动", "提问", "活动设计", "导入", "interaction", "activity"])
        needs_parent = self._contains_any(text, ["家长", "家校沟通", "沟通建议", "parent communication"])

        if needs_grading:
            add_action(
                thought="Start from grading output so correction feedback is immediately available.",
                action="homework_grading",
                action_input={"enableFederated": True},
            )
            if needs_error_push or self._contains_any(text, ["错题", "推题", "提升"]):
                add_action(
                    thought="Analyze mistakes and recommend targeted practice questions.",
                    action="error_analysis_question_push",
                    action_input={},
                )
            return self._slice_plan(actions)

        if needs_lesson_plan:
            if needs_diagnosis or self._contains_any(text, ["薄弱", "基础差", "学习困难", "弱项"]):
                add_action(
                    thought="Diagnose learner profile before generating a personalized lesson.",
                    action="student_diagnosis",
                    action_input={"enableFederated": True},
                )
            add_action(
                thought="Generate a personalized lesson plan from topic and learner context.",
                action="lesson_plan_generation",
                action_input={},
            )
            if needs_interaction or self._contains_any(text, ["导入", "互动", "提问"]):
                add_action(
                    thought="Design classroom interaction script aligned with the lesson plan.",
                    action="classroom_interaction_design",
                    action_input={},
                )
            return self._slice_plan(actions)

        if needs_report:
            add_action(
                thought="Build latest learner diagnosis as basis for report generation.",
                action="student_diagnosis",
                action_input={"enableFederated": True},
            )
            add_action(
                thought="Generate progress report with trends and recommendations.",
                action="progress_report_generation",
                action_input={},
            )
            return self._slice_plan(actions)

        if needs_path:
            add_action(
                thought="Assess current mastery before constructing study roadmap.",
                action="student_diagnosis",
                action_input={"enableFederated": True},
            )
            add_action(
                thought="Generate personalized weekly learning path.",
                action="learning_path_planning",
                action_input={},
            )
            return self._slice_plan(actions)

        if needs_parent:
            add_action(
                thought="Summarize learner strengths and gaps for parent-facing communication.",
                action="student_diagnosis",
                action_input={"enableFederated": True},
            )
            add_action(
                thought="Generate parent communication points and scripts.",
                action="parent_communication_suggestion",
                action_input={},
            )
            return self._slice_plan(actions)

        if needs_error_push:
            add_action(
                thought="Analyze wrong-question patterns and map knowledge gaps.",
                action="error_analysis_question_push",
                action_input={},
            )
            return self._slice_plan(actions)

        if needs_qa:
            add_action(
                thought="Provide guided tutoring answer with progressive hints.",
                action="tutoring_qa",
                action_input={},
            )
            return self._slice_plan(actions)

        if needs_interaction:
            add_action(
                thought="Design engagement-oriented classroom interaction strategy.",
                action="classroom_interaction_design",
                action_input={},
            )
            return self._slice_plan(actions)

        # Default full teacher chain for ambiguous requests.
        add_action(
            thought="Start from learner diagnosis to anchor personalization.",
            action="student_diagnosis",
            action_input={"enableFederated": True},
        )
        add_action(
            thought="Generate a baseline lesson plan for requested topic.",
            action="lesson_plan_generation",
            action_input={},
        )
        add_action(
            thought="Add a practical weekly learning roadmap.",
            action="learning_path_planning",
            action_input={},
        )
        return self._slice_plan(actions)

