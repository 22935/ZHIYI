from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from app.rag.legal_document_loader import LegalDocument


@dataclass
class LegalChunk:
    id: str
    document_id: str
    title: str
    content: str
    source_type: str
    source_name: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class LegalTextSplitter:
    def __init__(self, *, max_chars: int = 700):
        self.max_chars = max(200, max_chars)

    def split(self, documents: List[LegalDocument]) -> List[LegalChunk]:
        chunks: List[LegalChunk] = []
        for document in documents:
            sections = self._sections(document.content)
            for index, section in enumerate(sections, start=1):
                for part_index, part in enumerate(self._split_long(section), start=1):
                    chunk_id = f"{document.id}#chunk-{index}-{part_index}"
                    chunks.append(
                        LegalChunk(
                            id=chunk_id,
                            document_id=document.id,
                            title=document.title,
                            content=part,
                            source_type=document.source_type,
                            source_name=document.source_name,
                            metadata=dict(document.metadata),
                        )
                    )
        return chunks

    @staticmethod
    def _sections(content: str) -> List[str]:
        sections: List[str] = []
        current: List[str] = []
        for line in content.splitlines():
            if line.startswith("## ") and current:
                sections.append("\n".join(current).strip())
                current = [line]
            else:
                current.append(line)
        if current:
            sections.append("\n".join(current).strip())
        return [section for section in sections if section]

    def _split_long(self, section: str) -> List[str]:
        if len(section) <= self.max_chars:
            return [section]
        parts: List[str] = []
        current = ""
        for paragraph in section.split("\n\n"):
            if len(current) + len(paragraph) + 2 > self.max_chars and current:
                parts.append(current.strip())
                current = paragraph
            else:
                current = f"{current}\n\n{paragraph}" if current else paragraph
        if current:
            parts.append(current.strip())
        return parts


__all__ = ["LegalChunk", "LegalTextSplitter"]
