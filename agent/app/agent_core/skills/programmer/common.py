import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

APP_DIR = Path(__file__).resolve().parents[3]
PROGRAMMER_PROMPT_DIR = APP_DIR / "prompts" / "programmer"


class ProgrammerSkillHelper:
    @staticmethod
    def load_prompt(filename: str, fallback: str) -> str:
        path = PROGRAMMER_PROMPT_DIR / filename
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
    def extract_mermaid_code(text: str) -> str:
        raw = (text or "").strip()
        if not raw:
            return ""

        mermaid_fenced = re.search(r"```(?:mermaid)?\s*([\s\S]*?)```", raw, flags=re.IGNORECASE)
        if mermaid_fenced:
            return mermaid_fenced.group(1).strip()

        # direct diagram syntax fallback
        if raw.startswith(("graph ", "flowchart ", "sequenceDiagram", "classDiagram", "stateDiagram", "erDiagram")):
            return raw
        return ""

    @staticmethod
    def to_int(value: Any, default: int = 0) -> int:
        try:
            return int(float(value))
        except Exception:
            return default

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
    def compact_code_context(items: List[Dict[str, Any]], max_items: int = 5) -> str:
        blocks: List[str] = []
        for item in (items or [])[: max(1, max_items)]:
            metadata = item.get("metadata", {}) if isinstance(item, dict) else {}
            file_path = str(metadata.get("file_path", ""))
            function_name = str(metadata.get("function_name", ""))
            class_name = str(metadata.get("class_name", ""))
            header = file_path
            if class_name:
                header += f"::{class_name}"
            if function_name:
                header += f"::{function_name}"
            content = str(item.get("content", ""))[:1000]
            blocks.append(f"[{header}]\n{content}")
        return "\n\n".join(blocks).strip()

    @staticmethod
    def default_mermaid(diagram_type: str = "flowchart") -> str:
        normalized = (diagram_type or "flowchart").strip().lower()
        if normalized in {"sequence", "sequence_diagram", "sequence diagram"}:
            return (
                "sequenceDiagram\n"
                "  participant U as User\n"
                "  participant S as Service\n"
                "  U->>S: Request\n"
                "  S-->>U: Response"
            )
        if normalized in {"class", "class_diagram", "class diagram"}:
            return (
                "classDiagram\n"
                "  class Controller\n"
                "  class Service\n"
                "  class Repository\n"
                "  Controller --> Service\n"
                "  Service --> Repository"
            )
        return (
            "flowchart TD\n"
            "  A[Start] --> B[Analyze Requirement]\n"
            "  B --> C[Search Codebase]\n"
            "  C --> D[Generate Code]\n"
            "  D --> E[Render Diagram]"
        )

    @staticmethod
    def merge_fallback_json(base: Dict[str, Any], candidate: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        result = dict(base or {})
        if not isinstance(candidate, dict):
            return result
        for key, value in candidate.items():
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            if isinstance(value, list) and not value:
                continue
            result[key] = value
        return result
