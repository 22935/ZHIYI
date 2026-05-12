import asyncio
import json
import logging
import os
from typing import Any, Dict, List
from uuid import uuid4

from fastapi import APIRouter

from app.api.language_guard import ensure_simplified_chinese
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
tool_router = ToolRouter(enabled_roles=["writer"])
executor = ReactExecutor(tool_router=tool_router)
AGENT_SYNTHESIS_TIMEOUT = float(os.getenv("AGENT_SYNTHESIS_TIMEOUT", "180"))
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
    root = str(tree.get("label", "")).strip() or "故事"
    children = tree.get("children", []) if isinstance(tree.get("children"), list) else []
    branch_labels = []
    for child in children[:5]:
        if isinstance(child, dict):
            label = str(child.get("label", "")).strip()
            if label:
                branch_labels.append(label)
    if branch_labels:
        return f"创意树已生成（主题：{root}）。关键分支：{', '.join(branch_labels)}。"
    return f"创意树已生成（主题：{root}）。"


def _summarize_relation_graph(payload: Dict[str, Any]) -> str:
    graph = payload.get("relation_graph", {})
    if not isinstance(graph, dict):
        return ""
    nodes = graph.get("nodes", []) if isinstance(graph.get("nodes"), list) else []
    edges = graph.get("edges", []) if isinstance(graph.get("edges"), list) else []
    return f"人物关系图已生成，共 {len(nodes)} 个角色、{len(edges)} 条关系。"


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
        "作家 Agent 结构化降级结果：",
        f"1) 用户请求：{user_text}",
        f"2) 已调用技能：{', '.join(skills_used) if skills_used else '无'}",
    ]

    for index, action in enumerate(skills_used, start=3):
        payload = observations.get(action, {})
        if isinstance(payload, dict):
            preview = json.dumps(payload, ensure_ascii=False)[:220]
        else:
            preview = str(payload)[:220]
        lines.append(f"{index}) {action}：{preview}")

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
                "你是一名专业写作助手。请基于结构化结果输出简洁、可执行的答复，并且必须始终使用简体中文。\n"
                "要求：\n"
                "1. 优先返回可直接使用的写作结果。\n"
                "2. 若包含图示，请简要说明其用途。\n"
                "3. 信息不足时，明确列出缺失字段。\n\n"
                f"用户请求：{user_text}\n\n"
                f"结构化结果：\n{context_text}"
            )
            try:
                llm_response = await asyncio.wait_for(
                    ai_service.generate_text(text=synthesis_prompt, context=history[-8:] if history else None),
                    timeout=AGENT_SYNTHESIS_TIMEOUT,
                )
                answer = (llm_response.get("text", "") or "").strip()
            except Exception:
                answer = ""

        if not answer:
            answer = _build_fallback_answer(user_text=user_text, skills_used=skills_used, observations=observations)

        answer = await ensure_simplified_chinese(answer, ai_service=ai_service, history=history)

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
            message="作家 Agent 工作流执行完成。",
            inspiration_expand=observations.get("inspiration_expand") if isinstance(observations, dict) else None,
            outline_generate=observations.get("outline_generate") if isinstance(observations, dict) else None,
            content_write=observations.get("content_write") if isinstance(observations, dict) else None,
            character_relation_map=observations.get("character_relation_map") if isinstance(observations, dict) else None,
        )
    except Exception as exc:
        logger.error("Writer agent chat failed", exc_info=True)
        return AgentWriterResponse(
            success=False,
            answer="抱歉，作家 Agent 当前不可用，请稍后重试。",
            sessionId=session_id,
            skillsUsed=[],
            trace=[],
            federated=_default_federated_info(),
            message="作家 Agent 执行失败。",
            error=str(exc),
        )
