from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.paths import AGENT_ROOT


DEFAULT_LEGAL_KNOWLEDGE_DIR = AGENT_ROOT / "knowledge" / "legal"
DEFAULT_RAG_DOCUMENTS_FILE = AGENT_ROOT / "data" / "rag" / "documents.json"
LEGAL_RAG_ROLE_IDS = {"lawyer", "legal", "law"}


@dataclass
class LegalDocument:
    id: str
    source_path: str
    title: str
    content: str
    source_type: str
    source_name: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class LegalDocumentLoader:
    def __init__(
        self,
        root_dir: Optional[Path] = None,
        *,
        uploaded_documents_file: Optional[Path] = None,
        include_uploaded_rag: bool = True,
    ):
        self.root_dir = Path(root_dir or DEFAULT_LEGAL_KNOWLEDGE_DIR)
        self.uploaded_documents_file = Path(uploaded_documents_file or DEFAULT_RAG_DOCUMENTS_FILE)
        self.include_uploaded_rag = include_uploaded_rag

    def load(self) -> List[LegalDocument]:
        documents: List[LegalDocument] = []
        if self.root_dir.exists():
            for path in self._iter_paths():
                document = self._load_path(path)
                if document and document.content.strip():
                    documents.append(document)
        if self.include_uploaded_rag:
            documents.extend(self._load_uploaded_rag_documents())
        return documents

    def _iter_paths(self) -> Iterable[Path]:
        yield from sorted(self.root_dir.rglob("*.md"))
        yield from sorted(self.root_dir.rglob("*.json"))

    def _load_path(self, path: Path) -> Optional[LegalDocument]:
        relative = path.relative_to(self.root_dir).as_posix()
        if path.suffix.lower() == ".json":
            return self._load_json(path, relative)
        return self._load_markdown(path, relative)

    def _load_markdown(self, path: Path, relative: str) -> LegalDocument:
        content = path.read_text(encoding="utf-8")
        title = self._title_from_markdown(content) or path.stem.replace("_", " ")
        source_type = self._source_type_for_path(path)
        return LegalDocument(
            id=relative,
            source_path=str(path),
            title=title,
            content=content,
            source_type=source_type,
            source_name=title,
            metadata={
                "lawName": title if source_type == "law" else "",
                "articleNo": "",
                "sourcePath": str(path),
                "demo": True,
            },
        )

    def _load_json(self, path: Path, relative: str) -> Optional[LegalDocument]:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        title = str(data.get("title") or path.stem.replace("_", " "))
        content_parts = [title, str(data.get("description") or "")]
        entries = data.get("entries")
        if isinstance(entries, list):
            for item in entries:
                if isinstance(item, dict):
                    content_parts.append(str(item.get("title") or ""))
                    content_parts.append(str(item.get("content") or ""))
        source_type = str(data.get("sourceType") or self._source_type_for_path(path))
        return LegalDocument(
            id=relative,
            source_path=str(path),
            title=title,
            content="\n".join(part for part in content_parts if part),
            source_type=source_type,
            source_name=str(data.get("sourceName") or title),
            metadata={
                "lawName": str(data.get("lawName") or ""),
                "articleNo": str(data.get("articleNo") or ""),
                "sourcePath": str(path),
                "demo": bool(data.get("demo", True)),
            },
        )

    def _load_uploaded_rag_documents(self) -> List[LegalDocument]:
        if not self.uploaded_documents_file.exists():
            return []
        try:
            data = json.loads(self.uploaded_documents_file.read_text(encoding="utf-8"))
        except Exception:
            return []
        if not isinstance(data, dict):
            return []

        documents: List[LegalDocument] = []
        for doc_id, item in sorted(data.items()):
            if not isinstance(item, dict):
                continue
            document = self._document_from_uploaded_rag_item(str(doc_id), item)
            if document and document.content.strip():
                documents.append(document)
        return documents

    def _document_from_uploaded_rag_item(self, doc_id: str, item: Dict[str, Any]) -> Optional[LegalDocument]:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        role_id = str(
            item.get("role_id")
            or metadata.get("role_id")
            or metadata.get("roleId")
            or metadata.get("domain")
            or ""
        ).strip().lower()
        if role_id not in LEGAL_RAG_ROLE_IDS:
            return None

        content = str(item.get("text") or "")
        if not content.strip():
            return None

        filename = str(item.get("filename") or f"{doc_id}.txt")
        title = (
            str(metadata.get("title") or "").strip()
            or self._title_from_markdown(content)
            or Path(filename).stem.replace("_", " ")
        )
        law_name = str(metadata.get("lawName") or metadata.get("law_name") or title).strip()
        source_type = str(metadata.get("sourceType") or metadata.get("source_type") or "uploaded_rag_document")
        source_name = str(metadata.get("sourceName") or metadata.get("source_name") or law_name or title)

        return LegalDocument(
            id=f"rag/{doc_id}/{filename}",
            source_path=f"rag://{doc_id}/{filename}",
            title=title,
            content=content,
            source_type=source_type,
            source_name=source_name,
            metadata={
                "lawName": law_name,
                "articleNo": str(metadata.get("articleNo") or metadata.get("article_no") or ""),
                "sourcePath": f"rag://{doc_id}/{filename}",
                "sourceUrl": str(metadata.get("sourceUrl") or metadata.get("source_url") or ""),
                "officialId": str(metadata.get("officialId") or metadata.get("bbbs") or ""),
                "docId": doc_id,
                "filename": filename,
                "roleId": role_id,
                "uploadTime": str(item.get("upload_time") or ""),
                "size": item.get("size"),
                "demo": bool(metadata.get("demo", False)),
            },
        )

    @staticmethod
    def _title_from_markdown(content: str) -> str:
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
        return ""

    @staticmethod
    def _source_type_for_path(path: Path) -> str:
        parts = {part.lower() for part in path.parts}
        if "laws" in parts:
            return "law"
        if "templates" in parts:
            return "template"
        return "internal_rule"


__all__ = [
    "DEFAULT_LEGAL_KNOWLEDGE_DIR",
    "DEFAULT_RAG_DOCUMENTS_FILE",
    "LEGAL_RAG_ROLE_IDS",
    "LegalDocument",
    "LegalDocumentLoader",
]
