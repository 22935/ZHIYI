from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.rag.legal_document_loader import DEFAULT_LEGAL_KNOWLEDGE_DIR, LegalDocumentLoader
from app.rag.legal_text_splitter import LegalTextSplitter
from app.rag.providers.keyword_retriever import KeywordLegalEvidenceRetriever


class LegalEvidenceRetriever(KeywordLegalEvidenceRetriever):
    def __init__(
        self,
        knowledge_dir: Optional[Path] = None,
        *,
        uploaded_documents_file: Optional[Path] = None,
        include_uploaded_rag: bool = True,
    ):
        loader = LegalDocumentLoader(
            knowledge_dir or DEFAULT_LEGAL_KNOWLEDGE_DIR,
            uploaded_documents_file=uploaded_documents_file,
            include_uploaded_rag=include_uploaded_rag,
        )
        splitter = LegalTextSplitter()
        super().__init__(chunks=splitter.split(loader.load()))


__all__ = ["LegalEvidenceRetriever"]
