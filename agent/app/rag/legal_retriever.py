from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.rag.legal_document_loader import DEFAULT_LEGAL_KNOWLEDGE_DIR, LegalDocumentLoader
from app.rag.legal_text_splitter import LegalTextSplitter
from app.rag.providers.keyword_retriever import KeywordLegalEvidenceRetriever


class LegalEvidenceRetriever(KeywordLegalEvidenceRetriever):
    def __init__(self, knowledge_dir: Optional[Path] = None):
        loader = LegalDocumentLoader(knowledge_dir or DEFAULT_LEGAL_KNOWLEDGE_DIR)
        splitter = LegalTextSplitter()
        super().__init__(chunks=splitter.split(loader.load()))


__all__ = ["LegalEvidenceRetriever"]
