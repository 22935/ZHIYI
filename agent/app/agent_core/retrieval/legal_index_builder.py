import json
import logging
import os
import re
from typing import Any, Callable, Dict, List

from app.agent_core.retrieval.chroma_client import chroma_legal_client

logger = logging.getLogger(__name__)


class LegalIndexBuilder:
    """Build and query legal vector indices with keyword fallback."""

    STATUTE_COLLECTION = "law_statutes"
    CASE_COLLECTION = "law_cases"
    EVIDENCE_COLLECTION = "evidence_rules"
    LIMITATION_COLLECTION = "limitation_rules"
    JURISDICTION_COLLECTION = "jurisdiction_rules"

    def __init__(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        self.data_dir = os.path.join(base_dir, "data", "legal")
        self.knowledge_base_md = os.path.join(base_dir, "data", "rag", "knowledge_base", "律师-法律知识库.md")
        self.statute_json = os.path.join(self.data_dir, "statutes.json")
        self.case_json = os.path.join(self.data_dir, "cases.json")
        self.evidence_json = os.path.join(self.data_dir, "evidence_rules.json")
        self.limitation_json = os.path.join(self.data_dir, "limitation_rules.json")
        self.jurisdiction_json = os.path.join(self.data_dir, "jurisdiction_rules.json")

        self._fallback_docs: Dict[str, List[Dict[str, object]]] = {}

        os.makedirs(self.data_dir, exist_ok=True)
        self._ensure_seed_files()

    def _ensure_seed_files(self) -> None:
        seeds: Dict[str, List[Dict[str, Any]]] = {
            self.statute_json: self._build_default_statutes(),
            self.case_json: self._build_default_cases(),
            self.evidence_json: self._build_default_evidence_rules(),
            self.limitation_json: self._build_default_limitation_rules(),
            self.jurisdiction_json: self._build_default_jurisdiction_rules(),
        }
        for path, rows in seeds.items():
            if not os.path.exists(path):
                with open(path, "w", encoding="utf-8") as file:
                    json.dump(rows, file, ensure_ascii=False, indent=2)

    def _build_default_statutes(self) -> List[Dict[str, str]]:
        return [
            {
                "id": "statute_civil_code_188",
                "title": "民法典 第188条 普通诉讼时效",
                "law_name": "中华人民共和国民法典",
                "article": "第188条",
                "content": "向人民法院请求保护民事权利的诉讼时效期间为三年。",
                "source": "seed",
            },
            {
                "id": "statute_labor_contract_82",
                "title": "劳动合同法 第82条 未签劳动合同双倍工资",
                "law_name": "中华人民共和国劳动合同法",
                "article": "第82条",
                "content": "用人单位未订立书面劳动合同的，应依法支付双倍工资。",
                "source": "seed",
            },
        ]

    def _build_default_cases(self) -> List[Dict[str, str]]:
        return [
            {
                "id": "case_seed_001",
                "title": "劳动争议双倍工资纠纷案",
                "case_no": "(2022)京民终100号",
                "court": "北京市第二中级人民法院",
                "summary": "劳动者主张未签劳动合同期间双倍工资，法院支持主要请求。",
                "reasoning": "用工事实成立且单位未及时签约，应承担法定责任。",
                "source": "seed",
            }
        ]

    def _build_default_evidence_rules(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": "evidence_rule_seed_001",
                "title": "电子数据真实性审查",
                "rule_type": "authenticity",
                "basis": "《民事诉讼证据规定》第90条",
                "content": "审查电子数据形成、存储、传输过程及完整性，必要时核验原始载体。",
                "keywords": ["电子数据", "微信", "聊天记录", "截图"],
                "source": "seed",
            }
        ]

    def _build_default_limitation_rules(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": "limitation_rule_seed_001",
                "title": "普通民事纠纷诉讼时效",
                "case_type": "一般民事",
                "years": 3,
                "basis": "《民法典》第188条",
                "content": "一般民事权利请求诉讼时效为三年，自知道或应知权利受侵害时起算。",
                "interrupt_events": ["提起诉讼", "申请仲裁", "对方同意履行", "催告并留痕"],
                "source": "seed",
            }
        ]

    def _build_default_jurisdiction_rules(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": "jurisdiction_rule_seed_001",
                "title": "一般地域管辖",
                "rule_type": "general_territorial",
                "basis": "《民事诉讼法》第21条",
                "content": "通常由被告住所地人民法院管辖；住所地与经常居住地不一致的，由经常居住地法院管辖。",
                "keywords": ["被告住所地", "经常居住地", "一般管辖"],
                "source": "seed",
            }
        ]

    def _load_json(self, path: str) -> List[Dict[str, Any]]:
        if not os.path.exists(path):
            return []
        for encoding in ("utf-8", "utf-8-sig"):
            try:
                with open(path, "r", encoding=encoding) as file:
                    data = json.load(file)
                    if isinstance(data, list):
                        return data
                    return []
            except Exception:
                continue
        logger.warning("Failed to load legal seed file %s", path)
        return []

    def _parse_statutes_from_markdown(self) -> List[Dict[str, str]]:
        if not os.path.exists(self.knowledge_base_md):
            return []

        statutes: List[Dict[str, str]] = []
        current_section = ""
        current_title = ""
        content_buffer: List[str] = []

        try:
            with open(self.knowledge_base_md, "r", encoding="utf-8", errors="ignore") as file:
                lines = file.readlines()
        except Exception:
            return []

        for raw in lines:
            line = raw.strip()
            if not line:
                continue

            if line.startswith("## "):
                current_section = line.replace("## ", "", 1).strip()
                continue

            if line.startswith("### "):
                if current_title and content_buffer:
                    statutes.append(
                        {
                            "id": f"md_statute_{len(statutes) + 1}",
                            "title": current_title,
                            "law_name": current_section or "法律知识",
                            "article": "",
                            "content": " ".join(content_buffer).strip(),
                            "source": "knowledge_base_md",
                        }
                    )
                current_title = line.replace("### ", "", 1).strip()
                content_buffer = []
                continue

            content_buffer.append(line)

        if current_title and content_buffer:
            statutes.append(
                {
                    "id": f"md_statute_{len(statutes) + 1}",
                    "title": current_title,
                    "law_name": current_section or "法律知识",
                    "article": "",
                    "content": " ".join(content_buffer).strip(),
                    "source": "knowledge_base_md",
                }
            )

        return statutes

    def _to_statute_doc(self, item: Dict[str, Any]) -> Dict[str, object]:
        text = (
            f"标题: {item.get('title', '')}\\n"
            f"法律: {item.get('law_name', '')}\\n"
            f"条文: {item.get('article', '')}\\n"
            f"内容: {item.get('content', '')}"
        )
        metadata = {
            "title": item.get("title", ""),
            "law_name": item.get("law_name", ""),
            "article": item.get("article", ""),
            "source": item.get("source", "unknown"),
            "doc_type": "statute",
        }
        return {"id": item.get("id", ""), "text": text, "metadata": metadata}

    def _to_case_doc(self, item: Dict[str, Any]) -> Dict[str, object]:
        text = (
            f"案名: {item.get('title', '')}\\n"
            f"案号: {item.get('case_no', '')}\\n"
            f"法院: {item.get('court', '')}\\n"
            f"案情摘要: {item.get('summary', '')}\\n"
            f"裁判要点: {item.get('reasoning', '')}"
        )
        metadata = {
            "title": item.get("title", ""),
            "case_no": item.get("case_no", ""),
            "court": item.get("court", ""),
            "source": item.get("source", "unknown"),
            "doc_type": "case",
        }
        return {"id": item.get("id", ""), "text": text, "metadata": metadata}

    def _to_rule_doc(self, item: Dict[str, Any], doc_type: str) -> Dict[str, object]:
        keywords = item.get("keywords", [])
        if isinstance(keywords, list):
            keyword_text = "、".join(str(value) for value in keywords)
        else:
            keyword_text = str(keywords)

        text = (
            f"标题: {item.get('title', '')}\\n"
            f"规则类型: {item.get('rule_type', item.get('case_type', ''))}\\n"
            f"法律依据: {item.get('basis', '')}\\n"
            f"内容: {item.get('content', '')}\\n"
            f"关键词: {keyword_text}"
        )
        years_value = item.get("years")
        years = int(years_value) if isinstance(years_value, (int, float)) else -1
        interrupt_events = item.get("interrupt_events", [])
        if isinstance(interrupt_events, list):
            interruption_text = "、".join(str(value) for value in interrupt_events)
        else:
            interruption_text = str(interrupt_events or "")

        metadata = {
            "title": item.get("title", ""),
            "rule_type": item.get("rule_type", item.get("case_type", "")),
            "basis": item.get("basis", ""),
            "source": item.get("source", "unknown"),
            "doc_type": doc_type,
            "years": years,
            "interrupt_events": interruption_text,
        }
        return {"id": item.get("id", ""), "text": text, "metadata": metadata}

    def _build_collection_docs(self, collection_name: str) -> List[Dict[str, object]]:
        collection_sources: Dict[str, tuple[List[Dict[str, Any]], Callable[[Dict[str, Any]], Dict[str, object]]]] = {
            self.STATUTE_COLLECTION: (
                self._load_json(self.statute_json) + self._parse_statutes_from_markdown(),
                self._to_statute_doc,
            ),
            self.CASE_COLLECTION: (self._load_json(self.case_json), self._to_case_doc),
            self.EVIDENCE_COLLECTION: (
                self._load_json(self.evidence_json),
                lambda row: self._to_rule_doc(row, "evidence_rule"),
            ),
            self.LIMITATION_COLLECTION: (
                self._load_json(self.limitation_json),
                lambda row: self._to_rule_doc(row, "limitation_rule"),
            ),
            self.JURISDICTION_COLLECTION: (
                self._load_json(self.jurisdiction_json),
                lambda row: self._to_rule_doc(row, "jurisdiction_rule"),
            ),
        }

        rows, mapper = collection_sources.get(collection_name, ([], lambda x: {}))
        docs = [mapper(item) for item in rows]
        return [doc for doc in docs if doc.get("id") and doc.get("text")]

    def ensure_indices(self, force: bool = False) -> None:
        collections = [
            self.STATUTE_COLLECTION,
            self.CASE_COLLECTION,
            self.EVIDENCE_COLLECTION,
            self.LIMITATION_COLLECTION,
            self.JURISDICTION_COLLECTION,
        ]
        if not chroma_legal_client.is_available():
            return

        for collection in collections:
            if not force and chroma_legal_client.collection_count(collection) > 0:
                continue
            docs = self._build_collection_docs(collection)
            chroma_legal_client.upsert_documents(collection, docs)
            logger.info("Collection initialized: %s count=%s", collection, len(docs))

    def _tokenize(self, text: str) -> List[str]:
        if not text:
            return []
        tokens = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]+", text.lower())
        if tokens:
            return tokens
        normalized = text.strip().lower()
        return [normalized] if normalized else []

    def _load_fallback_docs(self, collection_name: str) -> List[Dict[str, object]]:
        if collection_name in self._fallback_docs:
            return self._fallback_docs[collection_name]
        docs = self._build_collection_docs(collection_name)
        self._fallback_docs[collection_name] = docs
        return docs

    def _fallback_search(self, collection_name: str, query: str, top_k: int) -> List[Dict[str, object]]:
        docs = self._load_fallback_docs(collection_name)
        if not docs:
            return []

        tokens = self._tokenize(query)
        token_set = set(tokens)
        scored: List[Dict[str, object]] = []

        for doc in docs:
            text = str(doc.get("text", "")).lower()
            if not text:
                continue
            hit_count = sum(1 for token in token_set if token and token in text)
            score = hit_count / max(1, len(token_set)) if token_set else 0.0
            if score > 0:
                scored.append(
                    {
                        "id": doc.get("id", ""),
                        "content": doc.get("text", ""),
                        "metadata": doc.get("metadata", {}),
                        "score": round(float(score), 4),
                    }
                )

        if not scored:
            for doc in docs[: max(1, top_k)]:
                scored.append(
                    {
                        "id": doc.get("id", ""),
                        "content": doc.get("text", ""),
                        "metadata": doc.get("metadata", {}),
                        "score": 0.1,
                    }
                )

        scored.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
        return scored[: max(1, top_k)]

    def _vector_or_fallback(self, collection_name: str, query: str, top_k: int) -> List[Dict[str, object]]:
        if chroma_legal_client.is_available():
            try:
                self.ensure_indices()
                rows = chroma_legal_client.query(collection_name, query_text=query, top_k=top_k)
                if rows:
                    return rows
            except Exception as exc:
                logger.warning("Vector retrieval failed for %s, fallback keyword mode. error=%s", collection_name, exc)
        return self._fallback_search(collection_name, query, top_k)

    def search_statutes(self, query: str, top_k: int = 5) -> List[Dict[str, object]]:
        return self._vector_or_fallback(self.STATUTE_COLLECTION, query, top_k)

    def search_cases(self, query: str, top_k: int = 5) -> List[Dict[str, object]]:
        return self._vector_or_fallback(self.CASE_COLLECTION, query, top_k)

    def search_evidence_rules(self, query: str, top_k: int = 5) -> List[Dict[str, object]]:
        return self._vector_or_fallback(self.EVIDENCE_COLLECTION, query, top_k)

    def search_limitation_rules(self, query: str, top_k: int = 5) -> List[Dict[str, object]]:
        return self._vector_or_fallback(self.LIMITATION_COLLECTION, query, top_k)

    def search_jurisdiction_rules(self, query: str, top_k: int = 5) -> List[Dict[str, object]]:
        return self._vector_or_fallback(self.JURISDICTION_COLLECTION, query, top_k)


legal_index_builder = LegalIndexBuilder()


if __name__ == "__main__":
    legal_index_builder.ensure_indices(force=True)
    if chroma_legal_client.is_available():
        for collection in [
            legal_index_builder.STATUTE_COLLECTION,
            legal_index_builder.CASE_COLLECTION,
            legal_index_builder.EVIDENCE_COLLECTION,
            legal_index_builder.LIMITATION_COLLECTION,
            legal_index_builder.JURISDICTION_COLLECTION,
        ]:
            count = chroma_legal_client.collection_count(collection)
            print(f"{collection}: {count}")
