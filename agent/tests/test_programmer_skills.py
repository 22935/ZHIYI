import asyncio
import importlib
from typing import Any, Dict, List
from unittest.mock import patch

from app.api import agent_programmer
from app.agent_core.react.planner import ReactPlanner
from app.agent_core.schema.agent_types import AgentProgrammerRequest, SkillRequest
from app.agent_core.skills.programmer import (
    CodeGenerationSkill,
    CodebaseSemanticSearchSkill,
    DiagramGenerationSkill,
    RequirementAnalysisSkill,
)


class FakeAIService:
    async def generate_text(
        self,
        text: str,
        role_id: str = None,
        context: List[Dict[str, str]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        prompt = (text or "").lower()

        if "functional_requirements" in prompt or "technical specification" in prompt:
            return {
                "text": (
                    '{"functional_requirements":["validate input","create user session"],'
                    '"inputs":["username","password"],'
                    '"outputs":["token","user_profile"],'
                    '"boundary_conditions":["empty password"],'
                    '"acceptance_criteria":["login success returns token"],'
                    '"suggested_modules":["auth.service","session.manager"]}'
                )
            }

        if "mermaid" in prompt and "diagram" in prompt:
            return {
                "text": (
                    '{"title":"User Login Flow","diagram_type":"flowchart",'
                    '"mermaid_code":"flowchart TD\\nA[User] --> B[Login API]\\nB --> C[Token]"}'
                )
            }

        if "generate implementation code" in prompt or "generate code" in prompt:
            return {
                "text": (
                    '{"code":"def login(username, password):\\n    if not username or not password:\\n'
                    '        raise ValueError(\'invalid\')\\n    return {\\"token\\": \\"mock-token\\"}",'
                    '"explanation":"Generated login handler.",'
                    '"suggested_tests":["empty password should fail","valid credential should return token"]}'
                )
            }

        return {"text": "{}"}


def _build_request(text: str, action_input: Dict[str, Any]) -> SkillRequest:
    return SkillRequest(
        sessionId="programmer-test-session",
        text=text,
        actionInput=action_input,
        memory={"history": [{"role": "user", "content": text}]},
    )


async def _assert_timeout_fallback(skill, request: SkillRequest) -> None:
    module = importlib.import_module(skill.__class__.__module__)

    async def _timeout_wait_for(coro, timeout):
        try:
            coro.close()
        except Exception:
            pass
        raise asyncio.TimeoutError

    with patch.object(module.asyncio, "wait_for", new=_timeout_wait_for):
        result = await skill.run(request)
    assert result.success is True
    assert "timeout" in result.message.lower()


async def test_requirement_analysis_skill():
    skill = RequirementAnalysisSkill(ai_service=FakeAIService())
    request = _build_request(
        "请分析用户登录需求",
        {"requirement": "Design user login with username and password"},
    )
    result = await skill.run(request)
    assert result.success is True
    assert "functional_requirements" in result.output
    assert isinstance(result.output.get("inputs", []), list)
    await _assert_timeout_fallback(skill, request)


async def test_codebase_semantic_search_skill():
    skill = CodebaseSemanticSearchSkill()
    request = _build_request("搜索登录函数", {"query": "login function", "top_k": 3})
    module = importlib.import_module(skill.__class__.__module__)

    with patch.object(module, "build_code_index", return_value={"success": True, "indexed_docs": 2}), patch.object(
        module,
        "search_code",
        return_value=[
            {
                "id": "auth.py:login:12",
                "content": "def login(username, password): ...",
                "score": 0.93,
                "metadata": {
                    "file_path": "backend/src/auth.py",
                    "function_name": "login",
                    "class_name": None,
                    "language": "python",
                    "line": 12,
                },
            }
        ],
    ):
        result = await skill.run(request)

    assert result.success is True
    assert isinstance(result.output.get("hits", []), list)
    assert result.output.get("hits", [])[0].get("file_path") == "backend/src/auth.py"
    await _assert_timeout_fallback(skill, request)


async def test_code_generation_skill():
    skill = CodeGenerationSkill(ai_service=FakeAIService())
    request = _build_request(
        "生成登录代码",
        {
            "target_language": "python",
            "specification": {"requirement": "login API"},
            "context_hits": [
                {
                    "file_path": "backend/src/auth.py",
                    "function_name": "login",
                    "score": 0.9,
                    "content": "def login(username, password): ...",
                }
            ],
        },
    )
    result = await skill.run(request)
    assert result.success is True
    assert "code" in result.output
    await _assert_timeout_fallback(skill, request)


async def test_diagram_generation_skill():
    skill = DiagramGenerationSkill(ai_service=FakeAIService())
    request = _build_request(
        "生成登录流程图",
        {"query": "user login flow", "diagram_type": "flowchart"},
    )
    result = await skill.run(request)
    assert result.success is True
    assert "mermaid_code" in result.output
    await _assert_timeout_fallback(skill, request)


async def test_programmer_planner():
    planner = ReactPlanner()
    plan = planner.plan("分析这个项目并生成微服务架构图", history=[], role="programmer")
    actions = [item.action for item in plan]
    assert "requirement_analysis" in actions or "codebase_semantic_search" in actions
    assert "diagram_generation" in actions


async def test_programmer_route():
    fake_ai = FakeAIService()

    original_programmer_skills = dict(agent_programmer.tool_router.skills_by_role.get("programmer", {}))
    original_ai_service = agent_programmer.ai_service

    search_skill_module = importlib.import_module(
        "app.agent_core.skills.programmer.codebase_semantic_search_skill"
    )
    try:
        agent_programmer.tool_router.register_skills_for_role(
            "programmer",
            {
                "requirement_analysis": RequirementAnalysisSkill(ai_service=fake_ai),
                "codebase_semantic_search": CodebaseSemanticSearchSkill(),
                "code_generation": CodeGenerationSkill(ai_service=fake_ai),
                "diagram_generation": DiagramGenerationSkill(ai_service=fake_ai),
            },
        )
        agent_programmer.ai_service = fake_ai

        with patch.object(
            search_skill_module,
            "build_code_index",
            return_value={"success": True, "indexed_files": 1, "indexed_docs": 1},
        ), patch.object(
            search_skill_module,
            "search_code",
            return_value=[
                {
                    "id": "backend/src/auth.py:login:12",
                    "content": "def login(username, password): ...",
                    "score": 0.88,
                    "metadata": {
                        "file_path": "backend/src/auth.py",
                        "function_name": "login",
                        "class_name": None,
                        "language": "python",
                        "line": 12,
                    },
                }
            ],
        ):
            response = await agent_programmer.programmer_agent_chat(
                AgentProgrammerRequest(text="帮我生成一个用户登录流程图")
            )

        assert response.success is True
        assert len(response.skills_used) > 0
        assert response.diagram_generation is not None
    finally:
        agent_programmer.tool_router.register_skills_for_role("programmer", original_programmer_skills)
        agent_programmer.ai_service = original_ai_service


async def _main():
    await test_requirement_analysis_skill()
    print("[PASS] requirement_analysis")
    await test_codebase_semantic_search_skill()
    print("[PASS] codebase_semantic_search")
    await test_code_generation_skill()
    print("[PASS] code_generation")
    await test_diagram_generation_skill()
    print("[PASS] diagram_generation")
    await test_programmer_planner()
    print("[PASS] programmer_planner")
    await test_programmer_route()
    print("[PASS] programmer_route")


if __name__ == "__main__":
    asyncio.run(_main())
