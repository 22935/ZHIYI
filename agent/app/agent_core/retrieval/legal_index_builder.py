import json
import logging
import os
import re
from typing import Dict, List

from app.agent_core.retrieval.chroma_client import chroma_legal_client

logger = logging.getLogger(__name__)


class LegalIndexBuilder:
    """Builds legal statute/case indices with vector + keyword fallback modes."""

    STATUTE_COLLECTION = "law_statutes"
    CASE_COLLECTION = "law_cases"

    def __init__(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        self.data_dir = os.path.join(base_dir, "data", "legal")
        self.knowledge_base_md = os.path.join(base_dir, "data", "rag", "knowledge_base", "律师-法律知识库.md")
        self.statute_json = os.path.join(self.data_dir, "statutes.json")
        self.case_json = os.path.join(self.data_dir, "cases.json")
        self._fallback_statute_docs: List[Dict[str, object]] = []
        self._fallback_case_docs: List[Dict[str, object]] = []

        os.makedirs(self.data_dir, exist_ok=True)
        self._ensure_seed_files()

    def _ensure_seed_files(self) -> None:
        if not os.path.exists(self.statute_json):
            with open(self.statute_json, "w", encoding="utf-8") as file:
                json.dump(self._build_default_statutes(), file, ensure_ascii=False, indent=2)

        if not os.path.exists(self.case_json):
            with open(self.case_json, "w", encoding="utf-8") as file:
                json.dump(self._build_default_cases(), file, ensure_ascii=False, indent=2)

    def _build_default_statutes(self) -> List[Dict[str, str]]:
        return [
            {
                "id": "statute_civil_code_contract_465",
                "title": "民法典 第465条 合同效力",
                "law_name": "中华人民共和国民法典",
                "article": "第465条",
                "content": "依法成立的合同，受法律保护。依法成立的合同，仅对当事人具有法律约束力，但是法律另有规定的除外。",
                "source": "seed",
            },
            {
                "id": "statute_civil_code_contract_509",
                "title": "民法典 第509条 合同履行",
                "law_name": "中华人民共和国民法典",
                "article": "第509条",
                "content": "当事人应当按照约定全面履行自己的义务。并应当遵循诚信原则，根据合同的性质、目的和交易习惯履行通知、协助、保密等义务。",
                "source": "seed",
            },
            {
                "id": "statute_labor_contract_10",
                "title": "劳动合同法 第10条 书面劳动合同",
                "law_name": "中华人民共和国劳动合同法",
                "article": "第10条",
                "content": "建立劳动关系，应当订立书面劳动合同。已建立劳动关系，未同时订立书面劳动合同的，应当自用工之日起一个月内订立。",
                "source": "seed",
            },
            {
                "id": "statute_labor_contract_82",
                "title": "劳动合同法 第82条 未签劳动合同双倍工资",
                "law_name": "中华人民共和国劳动合同法",
                "article": "第82条",
                "content": "用人单位自用工之日起超过一个月不满一年未与劳动者订立书面劳动合同的，应当向劳动者每月支付二倍工资。",
                "source": "seed",
            },
            {
                "id": "statute_copyright_47",
                "title": "著作权法 第47条 侵权责任",
                "law_name": "中华人民共和国著作权法",
                "article": "第47条",
                "content": "未经著作权人许可使用其作品等侵犯著作权或者与著作权有关权利的，应当根据情况承担停止侵害、消除影响、赔礼道歉、赔偿损失等民事责任。",
                "source": "seed",
            },
        ]

    def _build_default_cases(self) -> List[Dict[str, str]]:
        return [
            {
                "id": "case_contract_001",
                "title": "合同违约损害赔偿纠纷案",
                "case_no": "(2022)民终001号",
                "court": "某省高级人民法院",
                "summary": "买卖合同履行中，一方未按约交付，法院认定构成违约并支持可得利益损失赔偿。",
                "reasoning": "重点审查合同约定、履行证据、违约与损失之间因果关系。",
                "source": "seed",
            },
            {
                "id": "case_labor_001",
                "title": "未签书面劳动合同双倍工资案",
                "case_no": "(2021)民终188号",
                "court": "某市中级人民法院",
                "summary": "劳动者主张未签劳动合同期间双倍工资，法院支持超过一个月部分请求。",
                "reasoning": "用工事实成立且单位未及时签约，应承担法定支付责任。",
                "source": "seed",
            },
            {
                "id": "case_ip_001",
                "title": "网络转载著作权侵权案",
                "case_no": "(2020)知民终77号",
                "court": "知识产权法院",
                "summary": "平台未经许可转载原创文章，被认定构成信息网络传播权侵权。",
                "reasoning": "未经许可使用作品，且不符合法定合理使用情形。",
                "source": "seed",
            },
            {
                "id": "case_contract_002",
                "title": "格式条款效力争议案",
                "case_no": "(2023)民终112号",
                "court": "某省高级人民法院",
                "summary": "经营者未尽提示说明义务，格式条款中的免责内容不产生效力。",
                "reasoning": "审查提示说明义务履行情况及条款公平性。",
                "source": "seed",
            },
            {
                "id": "case_labor_002",
                "title": "违法解除劳动合同赔偿案",
                "case_no": "(2022)民终301号",
                "court": "某市中级人民法院",
                "summary": "用人单位解除程序违法，法院判令支付赔偿金。",
                "reasoning": "解除理由与程序不符合法律规定，应承担违法解除责任。",
                "source": "seed",
            },
        ]

    def _load_json(self, path: str) -> List[Dict[str, str]]:
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as file:
                return json.load(file)
        except Exception as exc:
            logger.warning("Failed to load legal seed file %s: %s", path, exc)
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

    def _to_statute_doc(self, item: Dict[str, str]) -> Dict[str, object]:
        text = (
            f"标题: {item.get('title', '')}\n"
            f"法律: {item.get('law_name', '')}\n"
            f"条文: {item.get('article', '')}\n"
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

    def _to_case_doc(self, item: Dict[str, str]) -> Dict[str, object]:
        text = (
            f"案名: {item.get('title', '')}\n"
            f"案号: {item.get('case_no', '')}\n"
            f"法院: {item.get('court', '')}\n"
            f"案情摘要: {item.get('summary', '')}\n"
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

    def ensure_indices(self) -> None:
        if not chroma_legal_client.is_available():
            return

        statute_count = chroma_legal_client.collection_count(self.STATUTE_COLLECTION)
        case_count = chroma_legal_client.collection_count(self.CASE_COLLECTION)
        if statute_count > 0 and case_count > 0:
            return

        statutes = self._load_json(self.statute_json)
        markdown_statutes = self._parse_statutes_from_markdown()
        if markdown_statutes:
            statutes.extend(markdown_statutes)

        cases = self._load_json(self.case_json)
        statute_docs = [self._to_statute_doc(item) for item in statutes]
        case_docs = [self._to_case_doc(item) for item in cases]

        chroma_legal_client.upsert_documents(self.STATUTE_COLLECTION, statute_docs)
        chroma_legal_client.upsert_documents(self.CASE_COLLECTION, case_docs)

        logger.info("Legal indices initialized. statutes=%s cases=%s", len(statute_docs), len(case_docs))

    def _tokenize(self, text: str) -> List[str]:
        if not text:
            return []
        tokens = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", text.lower())
        if tokens:
            return tokens
        normalized = text.strip().lower()
        return [normalized] if normalized else []

    def _ensure_fallback_docs(self) -> None:
        if self._fallback_statute_docs and self._fallback_case_docs:
            return

        statutes = self._load_json(self.statute_json)
        markdown_statutes = self._parse_statutes_from_markdown()
        if markdown_statutes:
            statutes.extend(markdown_statutes)
        cases = self._load_json(self.case_json)

        self._fallback_statute_docs = [self._to_statute_doc(item) for item in statutes]
        self._fallback_case_docs = [self._to_case_doc(item) for item in cases]

    def _fallback_search(self, docs: List[Dict[str, object]], query: str, top_k: int) -> List[Dict[str, object]]:
        self._ensure_fallback_docs()
        if not docs:
            return []

        tokens = self._tokenize(query)
        scored: List[Dict[str, object]] = []

        for doc in docs:
            text = str(doc.get("text", "")).lower()
            if not text:
                continue
            hit_count = sum(1 for token in tokens if token and token in text)
            score = hit_count / max(1, len(set(tokens))) if tokens else 0.0
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

    def search_statutes(self, query: str, top_k: int = 5) -> List[Dict[str, object]]:
        if chroma_legal_client.is_available():
            try:
                self.ensure_indices()
                rows = chroma_legal_client.query(self.STATUTE_COLLECTION, query_text=query, top_k=top_k)
                if rows:
                    return rows
            except Exception as exc:
                logger.warning("Vector statute retrieval failed, fallback to keyword mode. error=%s", exc)
        return self._fallback_search(self._fallback_statute_docs, query, top_k)

    def search_cases(self, query: str, top_k: int = 5) -> List[Dict[str, object]]:
        if chroma_legal_client.is_available():
            try:
                self.ensure_indices()
                rows = chroma_legal_client.query(self.CASE_COLLECTION, query_text=query, top_k=top_k)
                if rows:
                    return rows
            except Exception as exc:
                logger.warning("Vector case retrieval failed, fallback to keyword mode. error=%s", exc)
        return self._fallback_search(self._fallback_case_docs, query, top_k)


legal_index_builder = LegalIndexBuilder()
