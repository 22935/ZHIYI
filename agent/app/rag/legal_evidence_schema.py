from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class LegalEvidence:
    id: str
    riskId: str
    stepId: str = "legal_evidence_match"
    sourceType: str = "mock"
    sourceName: str = ""
    title: str = ""
    content: str = ""
    citationText: str = ""
    chunkId: str = ""
    confidence: float = 0.0
    retrievalScore: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "riskId": self.riskId,
            "stepId": self.stepId,
            "sourceType": self.sourceType,
            "sourceName": self.sourceName,
            "title": self.title,
            "content": self.content,
            "citationText": self.citationText,
            "chunkId": self.chunkId,
            "confidence": float(self.confidence),
            "retrievalScore": float(self.retrievalScore),
            "metadata": {
                "lawName": "",
                "articleNo": "",
                "sourcePath": "",
                **(self.metadata or {}),
            },
        }


def normalize_evidence(value: Dict[str, Any], *, risk_id: Optional[str] = None) -> Dict[str, Any]:
    metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
    evidence = LegalEvidence(
        id=str(value.get("id") or ""),
        riskId=str(value.get("riskId") or risk_id or ""),
        stepId=str(value.get("stepId") or "legal_evidence_match"),
        sourceType=str(value.get("sourceType") or "mock"),
        sourceName=str(value.get("sourceName") or ""),
        title=str(value.get("title") or ""),
        content=str(value.get("content") or ""),
        citationText=str(value.get("citationText") or ""),
        chunkId=str(value.get("chunkId") or ""),
        confidence=float(value.get("confidence") or 0.0),
        retrievalScore=float(value.get("retrievalScore") or 0.0),
        metadata=metadata,
    )
    return evidence.to_dict()


__all__ = ["LegalEvidence", "normalize_evidence"]
