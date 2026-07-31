"""Legal basis retrieval backed by the local read-only knowledge tool."""

import json

from agentos.agents.base import AgentOutput, AgentProfile, BaseAgent
from packs.legal.agents.common import case_text


class StatuteAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            AgentProfile(
                agentName="statute",
                domain="legal",
                capabilities=["statute_retrieval", "legal_basis"],
                allowedSkills=["statute_retrieval", "case_retrieval"],
                allowedTools=[
                    "knowledge_search",
                    "current_datetime",
                ],
                description="Finds legal basis for the current dispute and preserves its sources.",
            )
        )

    async def run(self, context):
        text = case_text(context.task.input)
        if context.tool_runtime is None:
            raise RuntimeError("legal evidence tool runtime is not configured")
        result = await context.tool_runtime.execute(
            "knowledge_search",
            {"query": text[:500], "top_k": 5},
        )
        try:
            envelope = json.loads(result.text)
        except (TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("local legal knowledge search returned an invalid payload") from exc
        if not envelope.get("ok"):
            raise RuntimeError(
                "local legal knowledge search failed: "
                f"{envelope.get('error') or 'unknown error'}"
            )
        sources = [item.public_dict() for item in result.sources]
        evidence_refs = [item.citation_id for item in result.sources]
        if not evidence_refs:
            raise RuntimeError(
                "offline legal basis retrieval requires a local knowledge source"
            )
        legal_basis = [
            str(item.get("snippet") or item.get("content") or "").strip()
            for item in ((envelope.get("data") or {}).get("results") or [])
            if isinstance(item, dict)
            and str(item.get("snippet") or item.get("content") or "").strip()
        ]
        return AgentOutput(
            output={
                "legal_basis": legal_basis,
                "query": text[:500],
                "retrieval_status": "completed",
                "sources": sources,
                "evidence_refs": evidence_refs,
            },
            summary=f"Retrieved legal basis from {len(evidence_refs)} source(s).",
            sources=sources,
            toolExecutions=[item.public_dict() for item in result.tool_executions],
            evidenceRefs=evidence_refs,
        )
