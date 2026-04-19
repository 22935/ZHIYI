import asyncio
import logging
from typing import Any, Dict, List

from app.agent_core.retrieval.code_index_builder import build_code_index, search_code
from app.agent_core.schema.agent_types import SkillRequest, SkillResult
from app.agent_core.skills.base import BaseSkill
from app.agent_core.skills.programmer.common import ProgrammerSkillHelper

logger = logging.getLogger(__name__)


class CodebaseSemanticSearchSkill(BaseSkill):
    def __init__(self):
        super().__init__("codebase_semantic_search")

    def _fallback_output(self, query: str, reason: str) -> Dict[str, Any]:
        return {
            "query": query,
            "top_k": 5,
            "hits": [],
            "index_status": {
                "success": False,
                "message": f"fallback: {reason}",
            },
        }

    def _normalize_hits(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for item in rows or []:
            metadata = item.get("metadata", {}) if isinstance(item, dict) else {}
            normalized.append(
                {
                    "id": item.get("id", ""),
                    "content": item.get("content", ""),
                    "score": item.get("score", 0.0),
                    "file_path": metadata.get("file_path"),
                    "function_name": metadata.get("function_name"),
                    "class_name": metadata.get("class_name"),
                    "language": metadata.get("language"),
                    "line": metadata.get("line"),
                    "metadata": metadata,
                }
            )
        return normalized

    async def execute(self, request: SkillRequest) -> SkillResult:
        action_input = request.action_input or {}
        query = str(action_input.get("query", request.text or "")).strip()
        top_k = max(1, min(20, ProgrammerSkillHelper.to_int(action_input.get("top_k"), 5)))
        root_path = str(action_input.get("root_path", "")).strip() or None

        index_status = build_code_index(root_path=root_path)
        rows = search_code(query=query, top_k=top_k)
        hits = self._normalize_hits(rows)

        output = {
            "query": query,
            "top_k": top_k,
            "hits": hits,
            "index_status": index_status,
        }
        return SkillResult(
            skillName=self.name,
            success=True,
            output=output,
            message=f"Codebase semantic search completed with {len(hits)} hit(s).",
        )

    async def run(self, request: SkillRequest) -> SkillResult:
        query = str((request.action_input or {}).get("query", request.text or "")).strip()
        try:
            return await asyncio.wait_for(self.execute(request), timeout=10)
        except asyncio.TimeoutError:
            return SkillResult(
                skillName=self.name,
                success=True,
                output=self._fallback_output(query=query, reason="timeout"),
                message="Codebase semantic search timeout, fallback returned.",
            )
        except Exception as exc:
            logger.error("CodebaseSemanticSearchSkill failed: %s", exc, exc_info=True)
            return SkillResult(
                skillName=self.name,
                success=True,
                output=self._fallback_output(query=query, reason="error"),
                message="Codebase semantic search error, fallback returned.",
            )
