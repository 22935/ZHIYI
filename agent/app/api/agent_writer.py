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
from app.agent_core.schema.agent_types import AgentWriterRequest, AgentWriterResponse
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
        "role": "writer",
        "query": user_text,
        "skills_used": skills_used,
    }
    if isinstance(observations, dict):
        inspiration = observations.get("inspiration_expand")
        if isinstance(inspiration, dict):
            creative_tree = inspiration.get("creative_tree")
            if isinstance(creative_tree, dict):
                payload["creative_tree_root"] = creative_tree.get("label")
                payload["creative_branch_count"] = len(creative_tree.get("children", []) or [])
        relation = observations.get("character_relation_map")
        if isinstance(relation, dict):
            relation_graph = relation.get("relation_graph")
            if isinstance(relation_graph, dict):
                nodes = relation_graph.get("nodes", []) if isinstance(relation_graph.get("nodes"), list) else []
                edges = relation_graph.get("edges", []) if isinstance(relation_graph.get("edges"), list) else []
                payload["relation_nodes"] = len(nodes)
                payload["relation_edges"] = len(edges)

    enhancement = await federated_adapter.get_risk_enhancement(payload)
    if not enhancement:
        return info

    info["applied"] = True
    info["risk_adjustment"] = round(float(enhancement.get("risk_adjustment", 0.0) or 0.0), 4)
    info["confidence"] = round(float(enhancement.get("confidence", 0.0) or 0.0), 4)
    info["federated_nodes_count"] = int(enhancement.get("federated_nodes_count", 0) or 0)
    return info


def _build_writer_context(observations: Dict[str, Any]) -> str:
    sections: List[str] = []
    mapping = [
        ("inspiration_expand", observations.get("inspiration_expand", {})),
        ("outline_generate", observations.get("outline_generate", {})),
        ("content_write", observations.get("content_write", {})),
        ("character_relation_map", observations.get("character_relation_map", {})),
    ]
    for title, payload in mapping:
        if payload:
            sections.append(f"[{title}]")
            sections.append(json.dumps(payload, ensure_ascii=False))
    return "\n".join(sections)


def _summarize_creative_tree(payload: Dict[str, Any]) -> str:
    tree = payload.get("creative_tree", {})
    if not isinstance(tree, dict):
        return ""
    root = str(tree.get("label", "")).strip() or "Story"
    children = tree.get("children", []) if isinstance(tree.get("children"), list) else []
    branch_labels = []
    for child in children[:5]:
        if isinstance(child, dict):
            label = str(child.get("label", "")).strip()
            if label:
                branch_labels.append(label)
    if branch_labels:
        return f"Creative tree ready for '{root}'. Key branches: {', '.join(branch_labels)}."
    return f"Creative tree ready for '{root}'."


def _summarize_relation_graph(payload: Dict[str, Any]) -> str:
    graph = payload.get("relation_graph", {})
    if not isinstance(graph, dict):
        return ""
    nodes = graph.get("nodes", []) if isinstance(graph.get("nodes"), list) else []
    edges = graph.get("edges", []) if isinstance(graph.get("edges"), list) else []
    return f"Character relation graph generated with {len(nodes)} characters and {len(edges)} relations."


def _extract_preferred_answer(skills_used: List[str], observations: Dict[str, Any]) -> str:
    used_set = set(skills_used or [])

    if "content_write" in used_set:
        payload = observations.get("content_write", {})
        if isinstance(payload, dict):
            text = str(payload.get("content", "")).strip()
            if text:
                return text

    if "outline_generate" in used_set:
        payload = observations.get("outline_generate", {})
        if isinstance(payload, dict):
            text = str(payload.get("outline_markdown", "")).strip()
            if text:
                return text

    if "inspiration_expand" in used_set:
        payload = observations.get("inspiration_expand", {})
        if isinstance(payload, dict):
            summary = _summarize_creative_tree(payload)
            if summary:
                return summary

    if "character_relation_map" in used_set:
        payload = observations.get("character_relation_map", {})
        if isinstance(payload, dict):
            summary = _summarize_relation_graph(payload)
            if summary:
                return summary

    return ""


def _build_fallback_answer(user_text: str, skills_used: List[str], observations: Dict[str, Any]) -> str:
    lines = [
        "WriterAgent structured fallback result:",
        f"1) User request: {user_text}",
        f"2) Skills used: {', '.join(skills_used) if skills_used else 'none'}",
    ]

    for index, action in enumerate(skills_used, start=3):
        payload = observations.get(action, {})
        if isinstance(payload, dict):
            preview = json.dumps(payload, ensure_ascii=False)[:220]
        else:
            preview = str(payload)[:220]
        lines.append(f"{index}) {action}: {preview}")

    return "\n".join(lines)


@router.post("/agent/writer/chat", response_model=AgentWriterResponse)
async def writer_agent_chat(request: AgentWriterRequest):
    session_id = request.session_id or str(uuid4())
    user_text = request.text

    try:
        history = session_memory_store.get_history(session_id)
        plan = planner.plan(user_text, history, role="writer")
        trace, skills_used, observations = await executor.execute(
            plan=plan,
            session_id=session_id,
            text=user_text,
            memory={"history": history},
            role="writer",
        )

        answer = _extract_preferred_answer(skills_used=skills_used, observations=observations)
        if not answer:
            context_text = _build_writer_context(observations)
            synthesis_prompt = (
                "You are a professional writing assistant. Provide a concise answer based on"
                " the structured outputs.\n"
                "Requirements:\n"
                "1. Return practical writing output first.\n"
                "2. If diagrams are generated, explain how to use them briefly.\n"
                "3. If information is missing, list exact fields needed.\n\n"
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

        return AgentWriterResponse(
            success=True,
            answer=answer,
            sessionId=session_id,
            skillsUsed=skills_used,
            trace=trace,
            federated=federated_info,
            message="Writer agent workflow completed.",
            inspiration_expand=observations.get("inspiration_expand") if isinstance(observations, dict) else None,
            outline_generate=observations.get("outline_generate") if isinstance(observations, dict) else None,
            content_write=observations.get("content_write") if isinstance(observations, dict) else None,
            character_relation_map=observations.get("character_relation_map") if isinstance(observations, dict) else None,
        )
    except Exception as exc:
        logger.error("Writer agent chat failed", exc_info=True)
        return AgentWriterResponse(
            success=False,
            answer="Sorry, writer agent is temporarily unavailable. Please try again later.",
            sessionId=session_id,
            skillsUsed=[],
            trace=[],
            federated=_default_federated_info(),
            message="Writer agent execution failed.",
            error=str(exc),
        )
