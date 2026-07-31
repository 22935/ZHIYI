"""Programmer Pack Agent backed by the real read-only code index."""

from __future__ import annotations

import json

from agentos.agents.base import AgentOutput, AgentProfile, BaseAgent


class CodebaseSearchAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            AgentProfile(
                agentName="codebase_search",
                domain="programmer",
                capabilities=["codebase_semantic_search"],
                allowedSkills=["codebase_semantic_search"],
                allowedTools=["codebase_search"],
                description="Finds reusable code in the current project through its real read-only index.",
            )
        )

    async def run(self, context):
        requirement = str(
            context.task.input.get("requirement") or context.task.title
        ).strip()
        if context.tool_runtime is None:
            raise RuntimeError("codebase search tool runtime is not configured")
        result = await context.tool_runtime.execute(
            "codebase_search", {"query": requirement[:500], "top_k": 5}
        )
        try:
            envelope = json.loads(result.text)
        except json.JSONDecodeError as exc:
            raise RuntimeError("codebase search returned an invalid payload") from exc
        if not envelope.get("ok"):
            raise RuntimeError(
                f"codebase search failed: {envelope.get('error') or 'unknown error'}"
            )
        hits = list((envelope.get("data") or {}).get("results") or [])
        sources = [item.public_dict() for item in result.sources]
        evidence_refs = [item.citation_id for item in result.sources]
        return AgentOutput(
            output={
                "query": requirement[:500],
                "top_k": 5,
                "hits": hits,
                "index_status": {
                    "success": True,
                    "message": f"Real code index search completed with {len(hits)} hit(s).",
                },
                "source_query": requirement[:160],
                "sources": sources,
                "evidence_refs": evidence_refs,
            },
            summary=f"Codebase search completed with {len(hits)} real hit(s).",
            sources=sources,
            toolExecutions=[item.public_dict() for item in result.tool_executions],
            evidenceRefs=evidence_refs,
        )
