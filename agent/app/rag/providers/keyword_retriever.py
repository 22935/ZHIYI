from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, Iterable, List, Set

from app.rag.legal_evidence_schema import LegalEvidence
from app.rag.legal_text_splitter import LegalChunk


class KeywordLegalEvidenceRetriever:
    retriever_type = "keyword"

    def __init__(self, *, chunks: List[LegalChunk]):
        self.chunks = chunks

    def retrieve(self, *, risk: Dict[str, Any], contract_type: str = "", top_k: int = 2) -> List[Dict[str, Any]]:
        query = " ".join(
            str(risk.get(field) or "")
            for field in ("title", "clause", "reason", "consequence", "suggestion")
        )
        if contract_type:
            query = f"{query} {contract_type}"
        keywords = self._keywords(query)
        if not keywords:
            return []

        scored = []
        for chunk in self.chunks:
            score = self._score(keywords, chunk)
            if score <= 0:
                continue
            scored.append((score, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)

        evidences: List[Dict[str, Any]] = []
        risk_id = str(risk.get("id") or "")
        for rank, (score, chunk) in enumerate(scored[: max(1, top_k)], start=1):
            evidence_id = self._evidence_id(risk_id, chunk.id, rank)
            metadata = {
                "lawName": str(chunk.metadata.get("lawName") or ""),
                "articleNo": str(chunk.metadata.get("articleNo") or ""),
                "sourcePath": str(chunk.metadata.get("sourcePath") or ""),
                "demo": bool(chunk.metadata.get("demo", True)),
            }
            confidence = min(0.95, 0.45 + score / 20)
            evidences.append(
                LegalEvidence(
                    id=evidence_id,
                    riskId=risk_id,
                    sourceType=chunk.source_type,
                    sourceName=chunk.source_name,
                    title=chunk.title,
                    content=chunk.content[:500],
                    citationText=self._citation(chunk),
                    chunkId=chunk.id,
                    confidence=round(confidence, 3),
                    retrievalScore=round(float(score), 3),
                    metadata=metadata,
                ).to_dict()
            )
        return evidences

    @staticmethod
    def _keywords(text: str) -> Set[str]:
        candidates = re.findall(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", text.lower())
        stopwords = {"合同", "风险", "基于", "文本", "本身", "条款", "可能", "双方", "建议", "责任"}
        words: Set[str] = set()
        for candidate in candidates:
            if candidate in stopwords:
                continue
            words.add(candidate)
            if re.search(r"[\u4e00-\u9fff]", candidate) and len(candidate) > 4:
                for index in range(0, len(candidate) - 1, 2):
                    gram = candidate[index : index + 2]
                    if gram not in stopwords:
                        words.add(gram)
        return words

    @classmethod
    def _score(cls, keywords: Iterable[str], chunk: LegalChunk) -> float:
        haystack = f"{chunk.title}\n{chunk.content}".lower()
        score = 0.0
        for keyword in keywords:
            count = haystack.count(keyword)
            if count:
                score += min(3, count) * (2.0 if len(keyword) >= 4 else 1.0)
        return score

    @staticmethod
    def _citation(chunk: LegalChunk) -> str:
        first_line = next((line.strip("# ").strip() for line in chunk.content.splitlines() if line.strip()), "")
        metadata = chunk.metadata or {}
        if metadata.get("demo", True):
            prefix = "演示资料，待正式法律知识库校验"
            return f"{prefix}：{first_line or chunk.title}"

        law_name = str(metadata.get("lawName") or chunk.source_name or "").strip()
        article_no = str(metadata.get("articleNo") or "").strip()
        if law_name and article_no:
            return f"《{law_name}》{article_no}"
        if law_name:
            return f"《{law_name}》：{first_line or chunk.title}"
        return f"{chunk.source_name or chunk.source_type}：{first_line or chunk.title}"

    @staticmethod
    def _evidence_id(risk_id: str, chunk_id: str, rank: int) -> str:
        digest = hashlib.sha1(f"{risk_id}:{chunk_id}:{rank}".encode("utf-8")).hexdigest()[:10]
        return f"ev-{digest}"


__all__ = ["KeywordLegalEvidenceRetriever"]
