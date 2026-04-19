import json
import logging
import os
from typing import Any, Dict, List, Optional

from app.agent_core.retrieval.chroma_client import chroma_client

logger = logging.getLogger(__name__)


class EducationIndexBuilder:
    """Build education vector indices for teacher agent workflows."""

    KNOWLEDGE_POINTS_COLLECTION = "edu_knowledge_points"
    QUESTION_BANK_COLLECTION = "edu_question_bank"
    LESSON_TEMPLATES_COLLECTION = "edu_lesson_templates"
    TEACHING_METHODS_COLLECTION = "edu_teaching_methods"

    def __init__(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        self.data_dir = os.path.join(base_dir, "data", "education")
        self.knowledge_points_json = os.path.join(self.data_dir, "knowledge_points.json")
        self.question_bank_json = os.path.join(self.data_dir, "question_bank.json")
        self.lesson_templates_json = os.path.join(self.data_dir, "lesson_templates.json")
        self.teaching_methods_json = os.path.join(self.data_dir, "teaching_methods.json")

    def _load_json(self, json_path: str) -> List[Dict[str, Any]]:
        path = json_path
        if not os.path.isabs(path):
            path = os.path.join(self.data_dir, json_path)

        if not os.path.exists(path):
            logger.warning("Education seed file not found: %s", path)
            return []

        for encoding in ("utf-8", "utf-8-sig"):
            try:
                with open(path, "r", encoding=encoding) as file:
                    rows = json.load(file)
                    if isinstance(rows, list):
                        return rows
            except Exception:
                continue

        logger.warning("Failed to load education seed file: %s", path)
        return []

    def _list_to_text(self, value: Any) -> str:
        if isinstance(value, list):
            return "、".join(str(item) for item in value)
        if value is None:
            return ""
        return str(value)

    def _list_to_json(self, value: Any) -> str:
        if isinstance(value, list):
            return json.dumps(value, ensure_ascii=False)
        if value is None:
            return "[]"
        return json.dumps([str(value)], ensure_ascii=False)

    def build_knowledge_point_index(self, json_path: Optional[str] = None) -> int:
        rows = self._load_json(json_path or self.knowledge_points_json)
        documents: List[Dict[str, Any]] = []

        for row in rows:
            row_id = str(row.get("id", "")).strip()
            if not row_id:
                continue

            prerequisites = row.get("prerequisites", [])
            text = (
                f"知识点: {row.get('name', '')}\n"
                f"学科: {row.get('subject', '')}\n"
                f"年级: {row.get('grade', '')}\n"
                f"前置知识: {self._list_to_text(prerequisites)}\n"
                f"掌握标准: {row.get('mastery_criteria', '')}\n"
                f"讲解内容: {row.get('vector_content', '')}"
            )
            metadata = {
                "name": str(row.get("name", "")),
                "subject": str(row.get("subject", "")),
                "grade": str(row.get("grade", "")),
                "prerequisites": self._list_to_json(prerequisites),
                "mastery_criteria": str(row.get("mastery_criteria", "")),
                "vector_content": str(row.get("vector_content", "")),
                "doc_type": "knowledge_point",
            }
            documents.append({"id": row_id, "text": text, "metadata": metadata})

        chroma_client.add_documents(self.KNOWLEDGE_POINTS_COLLECTION, documents)
        logger.info("Education collection initialized: %s count=%s", self.KNOWLEDGE_POINTS_COLLECTION, len(documents))
        return len(documents)

    def build_question_bank_index(self, json_path: Optional[str] = None) -> int:
        rows = self._load_json(json_path or self.question_bank_json)
        documents: List[Dict[str, Any]] = []

        for row in rows:
            row_id = str(row.get("id", "")).strip()
            if not row_id:
                continue

            knowledge_points = row.get("knowledge_points", [])
            text = (
                f"题目: {row.get('question_text', '')}\n"
                f"答案: {row.get('answer', '')}\n"
                f"知识点: {self._list_to_text(knowledge_points)}\n"
                f"难度: {row.get('difficulty', '')}\n"
                f"题型: {row.get('question_type', '')}\n"
                f"年级: {row.get('grade', '')}\n"
                f"学科: {row.get('subject', '')}"
            )
            metadata = {
                "question_text": str(row.get("question_text", "")),
                "answer": str(row.get("answer", "")),
                "subject": str(row.get("subject", "")),
                "grade": str(row.get("grade", "")),
                "difficulty": str(row.get("difficulty", "")),
                "question_type": str(row.get("question_type", "")),
                "knowledge_points": self._list_to_json(knowledge_points),
                "doc_type": "question",
            }
            documents.append({"id": row_id, "text": text, "metadata": metadata})

        chroma_client.add_documents(self.QUESTION_BANK_COLLECTION, documents)
        logger.info("Education collection initialized: %s count=%s", self.QUESTION_BANK_COLLECTION, len(documents))
        return len(documents)

    def build_lesson_template_index(self, json_path: Optional[str] = None) -> int:
        rows = self._load_json(json_path or self.lesson_templates_json)
        documents: List[Dict[str, Any]] = []

        for row in rows:
            row_id = str(row.get("id", "")).strip()
            if not row_id:
                continue

            structure = row.get("structure", [])
            text = (
                f"模板名称: {row.get('template_name', '')}\n"
                f"学科: {row.get('subject', '')}\n"
                f"年级: {row.get('grade', '')}\n"
                f"课型: {row.get('lesson_type', '')}\n"
                f"结构: {self._list_to_text(structure)}\n"
                f"样例内容: {row.get('sample_content', '')}"
            )
            metadata = {
                "template_name": str(row.get("template_name", "")),
                "subject": str(row.get("subject", "")),
                "grade": str(row.get("grade", "")),
                "lesson_type": str(row.get("lesson_type", "")),
                "structure": self._list_to_json(structure),
                "sample_content": str(row.get("sample_content", "")),
                "doc_type": "lesson_template",
            }
            documents.append({"id": row_id, "text": text, "metadata": metadata})

        chroma_client.add_documents(self.LESSON_TEMPLATES_COLLECTION, documents)
        logger.info("Education collection initialized: %s count=%s", self.LESSON_TEMPLATES_COLLECTION, len(documents))
        return len(documents)

    def build_teaching_method_index(self, json_path: Optional[str] = None) -> int:
        rows = self._load_json(json_path or self.teaching_methods_json)
        documents: List[Dict[str, Any]] = []

        for row in rows:
            row_id = str(row.get("id", "")).strip()
            if not row_id:
                continue

            scenarios = row.get("applicable_scenarios", [])
            steps = row.get("implementation_steps", [])
            examples = row.get("examples", [])
            text = (
                f"方法名称: {row.get('method_name', '')}\n"
                f"适用场景: {self._list_to_text(scenarios)}\n"
                f"实施步骤: {self._list_to_text(steps)}\n"
                f"案例示例: {self._list_to_text(examples)}"
            )
            metadata = {
                "method_name": str(row.get("method_name", "")),
                "applicable_scenarios": self._list_to_json(scenarios),
                "implementation_steps": self._list_to_json(steps),
                "examples": self._list_to_json(examples),
                "doc_type": "teaching_method",
            }
            documents.append({"id": row_id, "text": text, "metadata": metadata})

        chroma_client.add_documents(self.TEACHING_METHODS_COLLECTION, documents)
        logger.info("Education collection initialized: %s count=%s", self.TEACHING_METHODS_COLLECTION, len(documents))
        return len(documents)

    def build_all_indices(self) -> Dict[str, int]:
        return {
            self.KNOWLEDGE_POINTS_COLLECTION: self.build_knowledge_point_index(),
            self.QUESTION_BANK_COLLECTION: self.build_question_bank_index(),
            self.LESSON_TEMPLATES_COLLECTION: self.build_lesson_template_index(),
            self.TEACHING_METHODS_COLLECTION: self.build_teaching_method_index(),
        }


education_index_builder = EducationIndexBuilder()


def build_knowledge_point_index(json_path: str) -> int:
    return education_index_builder.build_knowledge_point_index(json_path)


def build_question_bank_index(json_path: str) -> int:
    return education_index_builder.build_question_bank_index(json_path)


def build_lesson_template_index(json_path: str) -> int:
    return education_index_builder.build_lesson_template_index(json_path)


def build_teaching_method_index(json_path: str) -> int:
    return education_index_builder.build_teaching_method_index(json_path)


if __name__ == "__main__":
    stats = education_index_builder.build_all_indices()
    print(json.dumps(stats, ensure_ascii=False, indent=2))
