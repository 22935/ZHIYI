import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.agent_core.retrieval.chroma_client import chroma_client
from app.agent_core.retrieval.education_index_builder import education_index_builder

logger = logging.getLogger(__name__)

APP_DIR = Path(__file__).resolve().parents[3]
EDU_DATA_DIR = APP_DIR / "data" / "education"
TEACHER_PROMPT_DIR = APP_DIR / "prompts" / "teacher"

_COLLECTION_TO_JSON = {
    education_index_builder.KNOWLEDGE_POINTS_COLLECTION: EDU_DATA_DIR / "knowledge_points.json",
    education_index_builder.QUESTION_BANK_COLLECTION: EDU_DATA_DIR / "question_bank.json",
    education_index_builder.LESSON_TEMPLATES_COLLECTION: EDU_DATA_DIR / "lesson_templates.json",
    education_index_builder.TEACHING_METHODS_COLLECTION: EDU_DATA_DIR / "teaching_methods.json",
}


class TeacherSkillHelper:
    _collection_ready: Dict[str, bool] = {}

    @staticmethod
    def load_prompt(filename: str, fallback: str) -> str:
        path = TEACHER_PROMPT_DIR / filename
        if path.exists():
            return path.read_text(encoding="utf-8", errors="ignore")
        return fallback

    @staticmethod
    def extract_json_obj(text: str) -> Dict[str, Any]:
        raw = (text or "").strip()
        if not raw:
            return {}

        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        fenced_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", raw, flags=re.IGNORECASE)
        if fenced_match:
            try:
                parsed = json.loads(fenced_match.group(1))
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass

        obj_match = re.search(r"(\{[\s\S]*\})", raw)
        if obj_match:
            try:
                parsed = json.loads(obj_match.group(1))
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass

        return {}

    @staticmethod
    def ensure_list(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            parts = re.split(r"[;,，、\n]", value)
            return [part.strip() for part in parts if part.strip()]
        text = str(value).strip()
        return [text] if text else []

    @staticmethod
    def to_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return default

    @staticmethod
    def to_int(value: Any, default: int = 0) -> int:
        try:
            return int(float(value))
        except Exception:
            return default

    @classmethod
    def _tokenize(cls, text: str) -> List[str]:
        if not text:
            return []
        tokens = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]+", text.lower())
        if tokens:
            return tokens
        lowered = text.strip().lower()
        return [lowered] if lowered else []

    @classmethod
    def _keyword_search_rows(
        cls,
        json_path: Path,
        query_text: str,
        top_k: int,
        fields: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        if not json_path.exists():
            return []

        try:
            rows = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            return []

        if not isinstance(rows, list) or not rows:
            return []

        tokens = set(cls._tokenize(query_text))
        if not tokens:
            tokens = set(cls._tokenize(" ".join(str(row) for row in rows[:3])))

        scored: List[Dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue

            if fields:
                corpus = " ".join(str(row.get(field, "")) for field in fields)
            else:
                corpus = json.dumps(row, ensure_ascii=False)
            lowered = corpus.lower()

            hit = sum(1 for token in tokens if token and token in lowered)
            score = hit / max(1, len(tokens))
            if score > 0:
                scored.append({"row": row, "score": round(score, 4)})

        if not scored:
            scored = [{"row": row, "score": 0.1} for row in rows[: max(1, top_k)]]

        scored.sort(key=lambda item: item["score"], reverse=True)
        return [item["row"] for item in scored[: max(1, top_k)]]

    @classmethod
    def _ensure_collection_index(cls, collection_name: str) -> None:
        if cls._collection_ready.get(collection_name):
            return

        try:
            if not chroma_client.is_available():
                cls._collection_ready[collection_name] = True
                return

            if collection_name == education_index_builder.KNOWLEDGE_POINTS_COLLECTION:
                education_index_builder.build_knowledge_point_index()
            elif collection_name == education_index_builder.QUESTION_BANK_COLLECTION:
                education_index_builder.build_question_bank_index()
            elif collection_name == education_index_builder.LESSON_TEMPLATES_COLLECTION:
                education_index_builder.build_lesson_template_index()
            elif collection_name == education_index_builder.TEACHING_METHODS_COLLECTION:
                education_index_builder.build_teaching_method_index()

            cls._collection_ready[collection_name] = True
        except Exception as exc:
            logger.warning("Failed ensuring collection %s: %s", collection_name, exc)
            cls._collection_ready[collection_name] = True

    @classmethod
    def query_collection(
        cls,
        collection_name: str,
        query_text: str,
        top_k: int = 5,
        fallback_fields: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        cls._ensure_collection_index(collection_name)

        rows: List[Dict[str, Any]] = []
        try:
            rows = chroma_client.query(collection_name=collection_name, query_text=query_text, top_k=top_k)
        except Exception as exc:
            logger.warning("Chroma query failed for %s: %s", collection_name, exc)
            rows = []

        if rows:
            for row in rows:
                metadata = row.get("metadata", {})
                if not isinstance(metadata, dict):
                    metadata = {}
                parsed = cls._parse_content_metadata(str(row.get("content", "")))
                merged = {**parsed, **metadata}
                row["metadata"] = merged
            return rows

        json_path = _COLLECTION_TO_JSON.get(collection_name)
        if json_path is None:
            return []

        fallback_rows = cls._keyword_search_rows(
            json_path=json_path,
            query_text=query_text,
            top_k=top_k,
            fields=fallback_fields,
        )

        wrapped: List[Dict[str, Any]] = []
        for row in fallback_rows:
            wrapped.append(
                {
                    "id": row.get("id", ""),
                    "content": json.dumps(row, ensure_ascii=False),
                    "metadata": row,
                    "score": 0.1,
                }
            )
        return wrapped

    @classmethod
    def _parse_content_metadata(cls, content: str) -> Dict[str, Any]:
        if not content:
            return {}

        parsed: Dict[str, Any] = {}
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if not value:
                continue

            mapping = {
                "题目": "question_text",
                "答案": "answer",
                "难度": "difficulty",
                "题型": "question_type",
                "年级": "grade",
                "学科": "subject",
                "掌握标准": "mastery_criteria",
                "模板名称": "template_name",
                "课型": "lesson_type",
                "结构": "structure",
                "样例内容": "sample_content",
                "方法名称": "method_name",
                "适用场景": "applicable_scenarios",
                "实施步骤": "implementation_steps",
                "案例示例": "examples",
            }

            if key == "知识点":
                mapped_key = "knowledge_points" if parsed.get("question_text") else "name"
                parsed[mapped_key] = value
                continue

            mapped_key = mapping.get(key)
            if mapped_key:
                parsed[mapped_key] = value

        return parsed

    @staticmethod
    def parse_scores(value: Any) -> List[float]:
        if isinstance(value, list):
            return [TeacherSkillHelper.to_float(item, -1) for item in value if TeacherSkillHelper.to_float(item, -1) >= 0]
        if isinstance(value, str):
            pieces = re.split(r"[;,，、\s]+", value.strip())
            scores = []
            for piece in pieces:
                if not piece:
                    continue
                parsed = TeacherSkillHelper.to_float(piece, -1)
                if parsed >= 0:
                    scores.append(parsed)
            return scores
        return []

    @staticmethod
    def clamp_score(score: float, low: float = 0.0, high: float = 100.0) -> float:
        return max(low, min(high, score))
