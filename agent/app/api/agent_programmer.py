import asyncio
import json
import logging
from typing import Any, Dict, List
from uuid import uuid4

from fastapi import APIRouter

from app.agent_core.federated.federated_adapter import FederatedAdapter
from app.agent_core.memory.session_memory import session_memory_store
from app.agent_core.react.executor import ReactExecutor
from app.agent_core.react.planner import ReactPlanner
from app.agent_core.react.tool_router import ToolRouter
from app.agent_core.schema.agent_types import AgentProgrammerRequest, AgentProgrammerResponse
from app.services.aiservice import AIService

logger = logging.getLogger(__name__)
router = APIRouter()

ai_service = AIService()
planner = ReactPlanner()
tool_router = ToolRouter()
executor = ReactExecutor(tool_router=tool_router)
federated_adapter = FederatedAdapter()


def _default_federated_info() -> Dict[str, Any]:
    return {
        "enabled": federated_adapter.enabled,
        "applied": False,
        "risk_adjustment": 0.0,
        "confidence": 0.0,
        "federated_nodes_count": 0,
    }


async def _collect_federated_info(user_text: str, skills_used: List[str], observations: Dict[str, Any]) -> Dict[str, Any]:
    info = _default_federated_info()
    if not federated_adapter.enabled:
        return info

    payload = {
        "role": "programmer",
        "query": user_text,
        "skills_used": skills_used,
    }
    if isinstance(observations, dict):
        requirement = observations.get("requirement_analysis")
        if isinstance(requirement, dict):
            payload["requirement_analysis"] = {
                "requirement": requirement.get("requirement"),
                "functional_requirements": requirement.get("functional_requirements", []),
            }
        search = observations.get("codebase_semantic_search")
        if isinstance(search, dict):
            hits = search.get("hits", []) if isinstance(search.get("hits"), list) else []
            payload["search_hit_count"] = len(hits)
            payload["search_files"] = [
                hit.get("file_path")
                for hit in hits[:5]
                if isinstance(hit, dict) and hit.get("file_path")
            ]

    enhancement = await federated_adapter.get_risk_enhancement(payload)
    if not enhancement:
        return info

    info["applied"] = True
    info["risk_adjustment"] = round(float(enhancement.get("risk_adjustment", 0.0) or 0.0), 4)
    info["confidence"] = round(float(enhancement.get("confidence", 0.0) or 0.0), 4)
    info["federated_nodes_count"] = int(enhancement.get("federated_nodes_count", 0) or 0)
    return info


def _build_programmer_context(observations: Dict[str, Any]) -> str:
    sections: List[str] = []
    mapping = [
        ("requirement_analysis", observations.get("requirement_analysis", {})),
        ("codebase_semantic_search", observations.get("codebase_semantic_search", {})),
        ("code_generation", observations.get("code_generation", {})),
        ("diagram_generation", observations.get("diagram_generation", {})),
    ]
    for title, payload in mapping:
        if payload:
            sections.append(f"[{title}]")
            sections.append(json.dumps(payload, ensure_ascii=False))
    return "\n".join(sections)


def _summarize_search(payload: Dict[str, Any]) -> str:
    hits = payload.get("hits", []) if isinstance(payload.get("hits"), list) else []
    if not hits:
        return "Code search completed with no direct matches."

    top_paths: List[str] = []
    for item in hits[:3]:
        if not isinstance(item, dict):
            continue
        path = str(item.get("file_path") or "")
        if path and path not in top_paths:
            top_paths.append(path)
    if top_paths:
        return f"Code search found {len(hits)} hits. Top files: {', '.join(top_paths)}."
    return f"Code search found {len(hits)} hits."


def _summarize_requirement(payload: Dict[str, Any]) -> str:
    requirement = str(payload.get("requirement", "")).strip() or "Requirement"
    fr = payload.get("functional_requirements", []) if isinstance(payload.get("functional_requirements"), list) else []
    io_inputs = payload.get("inputs", []) if isinstance(payload.get("inputs"), list) else []
    io_outputs = payload.get("outputs", []) if isinstance(payload.get("outputs"), list) else []

    lines = [
        f"Technical specification for: {requirement}",
        f"- Functional requirements: {len(fr)}",
        f"- Inputs: {len(io_inputs)}",
        f"- Outputs: {len(io_outputs)}",
    ]
    if fr:
        preview = "; ".join(str(item) for item in fr[:3])
        lines.append(f"- Key points: {preview}")
    return "\n".join(lines)


def _extract_preferred_answer(skills_used: List[str], observations: Dict[str, Any]) -> str:
    used_set = set(skills_used or [])

    if "diagram_generation" in used_set:
        payload = observations.get("diagram_generation", {})
        if isinstance(payload, dict):
            mermaid_code = str(payload.get("mermaid_code", "")).strip()
            diagram_type = str(payload.get("diagram_type", "")).strip()
            title = str(payload.get("title", "")).strip() or "Generated Diagram"
            if mermaid_code:
                prefix = f"{title} ({diagram_type})" if diagram_type else title
                return f"{prefix}\n\n```mermaid\n{mermaid_code}\n```"

    if "code_generation" in used_set:
        payload = observations.get("code_generation", {})
        if isinstance(payload, dict):
            code = str(payload.get("code", "")).strip()
            lang = str(payload.get("target_language", "")).strip()
            explanation = str(payload.get("explanation", "")).strip()
            if code:
                code_block = f"```{lang or 'text'}\n{code}\n```"
                if explanation:
                    return f"{explanation}\n\n{code_block}"
                return code_block

    if "requirement_analysis" in used_set:
        payload = observations.get("requirement_analysis", {})
        if isinstance(payload, dict):
            summary = _summarize_requirement(payload)
            if summary:
                return summary

    if "codebase_semantic_search" in used_set:
        payload = observations.get("codebase_semantic_search", {})
        if isinstance(payload, dict):
            summary = _summarize_search(payload)
            if summary:
                return summary

    return ""


def _build_fallback_answer(user_text: str, skills_used: List[str], observations: Dict[str, Any]) -> str:
    lines = [
        "ProgrammerAgent structured fallback result:",
        f"1) User request: {user_text}",
        f"2) Skills used: {', '.join(skills_used) if skills_used else 'none'}",
    ]

    for index, action in enumerate(skills_used, start=3):
        payload = observations.get(action, {})
        if isinstance(payload, dict):
            preview = json.dumps(payload, ensure_ascii=False)[:260]
        else:
            preview = str(payload)[:260]
        lines.append(f"{index}) {action}: {preview}")

    return "\n".join(lines)


@router.post("/agent/programmer/chat", response_model=AgentProgrammerResponse)
async def programmer_agent_chat(request: AgentProgrammerRequest):
    session_id = request.session_id or str(uuid4())
    user_text = request.text

    try:
        history = session_memory_store.get_history(session_id)
        plan = planner.plan(user_text, history, role="programmer")
        trace, skills_used, observations = await executor.execute(
            plan=plan,
            session_id=session_id,
            text=user_text,
            memory={"history": history},
            role="programmer",
        )

        answer = _extract_preferred_answer(skills_used=skills_used, observations=observations)
        if not answer:
            context_text = _build_programmer_context(observations)
            synthesis_prompt = (
                "You are a professional software engineering assistant. "
                "Synthesize a concise, actionable response from the structured outputs.\n"
                "Requirements:\n"
                "1. Return practical output first.\n"
                "2. If code is generated, include only essential explanation.\n"
                "3. If Mermaid is generated, include the mermaid code block.\n"
                "4. If information is missing, list exact fields needed.\n\n"
                f"User request: {user_text}\n\n"
                f"Structured outputs:\n{context_text}"
            )
            try:
                llm_response = await asyncio.wait_for(
                    ai_service.generate_text(text=synthesis_prompt, context=history[-8:] if history else None),
                    timeout=15,
                )
                answer = (llm_response.get("text", "") or "").strip()
            except Exception:
                answer = ""

        if not answer:
            answer = _build_fallback_answer(user_text=user_text, skills_used=skills_used, observations=observations)

        session_memory_store.append_message(session_id, "user", user_text)
        session_memory_store.append_message(session_id, "assistant", answer)
        federated_info = await _collect_federated_info(
            user_text=user_text,
            skills_used=skills_used,
            observations=observations if isinstance(observations, dict) else {},
        )

        return AgentProgrammerResponse(
            success=True,
            answer=answer,
            sessionId=session_id,
            skillsUsed=skills_used,
            trace=trace,
            federated=federated_info,
            message="Programmer agent workflow completed.",
            requirement_analysis=observations.get("requirement_analysis") if isinstance(observations, dict) else None,
            codebase_semantic_search=observations.get("codebase_semantic_search") if isinstance(observations, dict) else None,
            code_generation=observations.get("code_generation") if isinstance(observations, dict) else None,
            diagram_generation=observations.get("diagram_generation") if isinstance(observations, dict) else None,
        )
    except Exception as exc:
        logger.error("Programmer agent chat failed", exc_info=True)
        return AgentProgrammerResponse(
            success=False,
            answer="Sorry, programmer agent is temporarily unavailable. Please try again later.",
            sessionId=session_id,
            skillsUsed=[],
            trace=[],
            federated=_default_federated_info(),
            message="Programmer agent execution failed.",
            error=str(exc),
        )
