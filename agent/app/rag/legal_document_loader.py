from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.paths import AGENT_ROOT


DEFAULT_LEGAL_KNOWLEDGE_DIR = AGENT_ROOT / "knowledge" / "legal"


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
    def __init__(self, root_dir: Optional[Path] = None):
        self.root_dir = Path(root_dir or DEFAULT_LEGAL_KNOWLEDGE_DIR)

    def load(self) -> List[LegalDocument]:
        if not self.root_dir.exists():
            return []
        documents: List[LegalDocument] = []
        for path in self._iter_paths():
            document = self._load_path(path)
            if document and document.content.strip():
                documents.append(document)
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


__all__ = ["DEFAULT_LEGAL_KNOWLEDGE_DIR", "LegalDocument", "LegalDocumentLoader"]
