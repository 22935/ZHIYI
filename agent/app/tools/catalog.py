"""Implementations of the deliberately small, read-only tool catalog."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from tavily import AsyncTavilyClient

from app.config import settings
from app.tools.contracts import SourceReference, ToolPayload, ToolUnavailableError


def _now_iso() -> str:
    return datetime.now(ZoneInfo("UTC")).isoformat()


def _citation_id(provider: str, value: str) -> str:
    digest = hashlib.sha256(f"{provider}:{value}".encode("utf-8")).hexdigest()[:16]
    return f"src_{digest}"


def _trim(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _validate_query(query: str) -> str:
    value = str(query or "").strip()
    if not value:
        raise ValueError("query must not be empty")
    if len(value) > 500:
        raise ValueError("query must be at most 500 characters")
    return value


def _validate_public_url(value: str) -> str:
    raw = str(value or "").strip()
    if len(raw) > 2048:
        raise ValueError("URL is too long")
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("only absolute HTTP(S) URLs are allowed")
    if parsed.username or parsed.password:
        raise ValueError("URLs containing credentials are not allowed")
    host = parsed.hostname.lower()
    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError("local URLs are not allowed")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address and not address.is_global:
        raise ValueError("private or non-global IP addresses are not allowed")
    return raw


class ReadOnlyToolCatalog:
    """Dispatches only allowlisted read operations and normalizes their evidence."""

    TOOL_NAMES = (
        "web_search",
        "web_extract",
        "knowledge_search",
        "codebase_search",
        "current_datetime",
    )

    def __init__(self) -> None:
        self._tavily: AsyncTavilyClient | None = None

    def availability(self) -> dict[str, dict[str, Any]]:
        enabled = bool(settings.TOOL_RUNTIME_ENABLED)
        web = enabled and bool(settings.TAVILY_API_KEY.strip())
        return {
            "web_search": {"available": web, "provider": "tavily", "readOnly": True},
            "web_extract": {"available": web, "provider": "tavily", "readOnly": True},
            "knowledge_search": {"available": enabled, "provider": "configured-rag", "readOnly": True},
            "codebase_search": {"available": enabled, "provider": "agentos-code-index", "readOnly": True},
            "current_datetime": {"available": enabled, "provider": "system-clock", "readOnly": True},
        }

    def is_available(self, name: str) -> bool:
        return bool(self.availability().get(name, {}).get("available"))

    async def execute(
        self, name: str, arguments: dict[str, Any], *, role_id: str | None = None
    ) -> ToolPayload:
        if name not in self.TOOL_NAMES or not self.is_available(name):
            raise ToolUnavailableError(f"read-only tool is unavailable: {name}")
        return await getattr(self, f"_{name}")(arguments, role_id=role_id)

    async def warmup(self) -> dict[str, Any]:
        """Prepare local read-only indexes before the first user tool call."""
        if not self.is_available("codebase_search"):
            return {"codebase_search": {"status": "unavailable"}}
        _, _, metadata = await self._ensure_code_index()
        return {"codebase_search": {"status": "ready", **metadata}}

    def _tavily_client(self) -> AsyncTavilyClient:
        if self._tavily is None:
            key = settings.TAVILY_API_KEY.strip()
            if not key:
                raise ToolUnavailableError("Tavily API key is not configured")
            self._tavily = AsyncTavilyClient(api_key=key, client_source="kinlin-ai")
        return self._tavily

    async def _web_search(self, arguments: dict[str, Any], **_: Any) -> ToolPayload:
        query = _validate_query(arguments.get("query", ""))
        requested = int(arguments.get("max_results", settings.TOOL_SEARCH_MAX_RESULTS) or 1)
        max_results = max(1, min(requested, settings.TOOL_SEARCH_MAX_RESULTS, 5))
        topic = str(arguments.get("topic") or "general")
        if topic not in {"general", "news", "finance"}:
            topic = "general"
        response = await self._tavily_client().search(
            query=query,
            topic=topic,
            search_depth="advanced",
            max_results=max_results,
            include_answer=False,
            include_raw_content=False,
            timeout=settings.TOOL_TIMEOUT_SECONDS,
        )
        rows = [item for item in response.get("results", []) if isinstance(item, dict)]
        sources: list[SourceReference] = []
        results: list[dict[str, Any]] = []
        for item in rows[:max_results]:
            try:
                url = _validate_public_url(str(item.get("url") or ""))
            except ValueError:
                continue
            source = SourceReference(
                citationId=_citation_id("tavily", url),
                title=_trim(item.get("title") or url, 240),
                url=url,
                snippet=_trim(item.get("content"), 600),
                provider="tavily",
                retrievedAt=_now_iso(),
            )
            sources.append(source)
            results.append({
                "citationId": source.citation_id,
                "title": source.title,
                "url": source.url,
                "snippet": source.snippet,
                "score": item.get("score"),
            })
        return ToolPayload(
            summary=f"Found {len(results)} web result(s) for the query.",
            data={"results": results},
            sources=sources,
        )

    async def _web_extract(self, arguments: dict[str, Any], **_: Any) -> ToolPayload:
        raw_urls = arguments.get("urls") or []
        if isinstance(raw_urls, str):
            raw_urls = [raw_urls]
        if not isinstance(raw_urls, list) or not raw_urls:
            raise ValueError("urls must contain at least one URL")
        urls = [
            _validate_public_url(item)
            for item in raw_urls[: settings.TOOL_EXTRACT_MAX_URLS]
        ]
        response = await self._tavily_client().extract(
            urls=urls,
            extract_depth="advanced",
            format="markdown",
            timeout=settings.TOOL_TIMEOUT_SECONDS,
        )
        rows = [item for item in response.get("results", []) if isinstance(item, dict)]
        sources: list[SourceReference] = []
        results: list[dict[str, Any]] = []
        for item in rows[: settings.TOOL_EXTRACT_MAX_URLS]:
            try:
                url = _validate_public_url(str(item.get("url") or ""))
            except ValueError:
                continue
            content = str(item.get("raw_content") or item.get("content") or "")[:20000]
            source = SourceReference(
                citationId=_citation_id("tavily", url),
                title=_trim(item.get("title") or url, 240),
                url=url,
                snippet=_trim(content, 600),
                provider="tavily",
                retrievedAt=_now_iso(),
            )
            sources.append(source)
            results.append({"citationId": source.citation_id, "url": url, "content": content})
        return ToolPayload(
            summary=f"Extracted {len(results)} web page(s).",
            data={"results": results},
            sources=sources,
        )

    async def _knowledge_search(
        self, arguments: dict[str, Any], *, role_id: str | None = None
    ) -> ToolPayload:
        query = _validate_query(arguments.get("query", ""))
        top_k = max(1, min(int(arguments.get("top_k", 5) or 1), 5))
        from app.services.ragtoolsintegration import rag_tools_integration

        rows = await rag_tools_integration.search(query=query, top_k=top_k, role_id=role_id)
        sources: list[SourceReference] = []
        results: list[dict[str, Any]] = []
        for index, item in enumerate(rows[:top_k]):
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            doc_id = str(item.get("doc_id") or item.get("id") or f"result-{index + 1}")
            filename = str(item.get("filename") or metadata.get("filename") or "") or None
            url_value = metadata.get("url") or item.get("url")
            url = _validate_public_url(str(url_value)) if url_value else None
            content = _trim(item.get("content") or item.get("text"), 1200)
            source = SourceReference(
                citationId=_citation_id("knowledge", doc_id),
                title=filename or str(metadata.get("title") or f"Knowledge source {index + 1}"),
                filename=filename,
                url=url,
                snippet=content[:600],
                provider=str(item.get("method") or "knowledge"),
                retrievedAt=_now_iso(),
            )
            sources.append(source)
            results.append({
                "citationId": source.citation_id,
                "title": source.title,
                "content": content,
                "score": item.get("score"),
            })
        return ToolPayload(
            summary=f"Found {len(results)} local knowledge result(s).",
            data={"results": results},
            sources=sources,
        )

    async def _codebase_search(self, arguments: dict[str, Any], **_: Any) -> ToolPayload:
        query = _validate_query(arguments.get("query", ""))
        top_k = max(1, min(int(arguments.get("top_k", 5) or 1), 5))
        code_index_builder, base_root, _ = await self._ensure_code_index()
        rows = await asyncio.to_thread(
            code_index_builder.search_code,
            query,
            top_k,
            prefer_vectors=False,
        )
        if not rows:
            await asyncio.to_thread(
                code_index_builder.build_code_index,
                str(base_root),
                enable_vectors=False,
            )
            rows = await asyncio.to_thread(
                code_index_builder.search_code,
                query,
                top_k,
                prefer_vectors=False,
            )
        sources: list[SourceReference] = []
        results: list[dict[str, Any]] = []
        for item in rows[:top_k]:
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            file_path = str(metadata.get("file_path") or item.get("file_path") or "")
            resolved_path = (base_root / file_path).resolve()
            if not file_path or not resolved_path.is_relative_to(base_root):
                continue
            line = int(metadata.get("line") or item.get("line") or 1)
            content = str(item.get("content") or "")[:4000]
            reference = f"{file_path}:{line}"
            source = SourceReference(
                citationId=_citation_id("codebase", reference),
                title=reference,
                filename=file_path or None,
                snippet=_trim(content, 600),
                provider="codebase",
                retrievedAt=_now_iso(),
            )
            sources.append(source)
            results.append({
                "citationId": source.citation_id,
                "file_path": file_path,
                "line": line,
                "language": metadata.get("language"),
                "score": item.get("score"),
                "content": content,
                "index_root": str(base_root),
            })
        return ToolPayload(
            summary=f"Found {len(results)} real code index hit(s).",
            data={"results": results},
            sources=sources,
        )

    async def _ensure_code_index(self):
        from agentos.adapters.retrieval.code_index_builder import code_index_builder

        root = settings.TOOL_CODEBASE_ROOT.strip() or None
        base_root = Path(root).resolve() if root else code_index_builder._normalize_path(None)
        manifest = code_index_builder._load_json(
            code_index_builder.manifest_path,
            default={"root_path": ""},
        )
        indexed_root = str(manifest.get("root_path") or "").strip()
        if not indexed_root or Path(indexed_root).resolve() != base_root:
            await asyncio.to_thread(
                code_index_builder.build_code_index,
                str(base_root),
                enable_vectors=False,
            )
            manifest = code_index_builder._load_json(
                code_index_builder.manifest_path,
                default={"root_path": "", "files": {}},
            )
        return code_index_builder, base_root, {
            "root": str(base_root),
            "indexedFiles": len((manifest.get("files") or {})),
        }

    async def _current_datetime(self, arguments: dict[str, Any], **_: Any) -> ToolPayload:
        timezone_name = str(arguments.get("timezone") or "Asia/Shanghai").strip()
        if len(timezone_name) > 64:
            raise ValueError("timezone name is too long")
        try:
            zone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown timezone: {timezone_name}") from exc
        current = datetime.now(zone)
        return ToolPayload(
            summary=f"Current date and time in {timezone_name}.",
            data={
                "timezone": timezone_name,
                "iso": current.isoformat(),
                "date": current.date().isoformat(),
            },
        )


__all__ = ["ReadOnlyToolCatalog"]
