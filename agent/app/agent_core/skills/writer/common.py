import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

APP_DIR = Path(__file__).resolve().parents[3]
WRITER_PROMPT_DIR = APP_DIR / "prompts" / "writer"


class WriterSkillHelper:
    @staticmethod
    def load_prompt(filename: str, fallback: str) -> str:
        path = WRITER_PROMPT_DIR / filename
        if path.exists():
            return path.read_text(encoding="utf-8", errors="ignore")
        return fallback

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
    def _normalize_tree_node(node: Any, fallback_id: str, depth: int = 0, max_depth: int = 4) -> Dict[str, Any]:
        if depth > max_depth:
            return {"id": fallback_id, "label": "创意", "description": "", "children": []}

        data = node if isinstance(node, dict) else {}
        node_id = str(data.get("id", fallback_id)).strip() or fallback_id
        label = str(data.get("label", "创意")).strip() or "创意"
        description = str(data.get("description", "")).strip()

        children_raw = data.get("children", [])
        children: List[Dict[str, Any]] = []
        if isinstance(children_raw, list):
            for index, child in enumerate(children_raw[:8], start=1):
                children.append(
                    WriterSkillHelper._normalize_tree_node(
                        child,
                        fallback_id=f"{node_id}.{index}",
                        depth=depth + 1,
                        max_depth=max_depth,
                    )
                )

        return {
            "id": node_id,
            "label": label,
            "description": description,
            "children": children,
        }

    @staticmethod
    def default_creative_tree(premise: str) -> Dict[str, Any]:
        seed = (premise or "故事创意").strip() or "故事创意"
        return {
            "id": "root",
            "label": seed,
            "description": "核心前提",
            "children": [
                {
                    "id": "root.world",
                    "label": "世界设定",
                    "description": "故事发生的时空背景",
                    "children": [],
                },
                {
                    "id": "root.character",
                    "label": "主角成长弧",
                    "description": "角色成长路径与内在冲突",
                    "children": [],
                },
                {
                    "id": "root.conflict",
                    "label": "核心冲突",
                    "description": "主要阻力与风险代价",
                    "children": [],
                },
                {
                    "id": "root.ending",
                    "label": "可能结局",
                    "description": "至少两种结局走向",
                    "children": [],
                },
            ],
        }

    @staticmethod
    def normalize_creative_tree(payload: Dict[str, Any], premise: str) -> Dict[str, Any]:
        tree = payload.get("creative_tree", payload)
        if not isinstance(tree, dict):
            return WriterSkillHelper.default_creative_tree(premise)

        normalized = WriterSkillHelper._normalize_tree_node(tree, fallback_id="root")
        if normalized.get("id") == "root" and not normalized.get("label"):
            normalized["label"] = premise or "故事创意"
        if not normalized.get("label"):
            normalized["label"] = premise or "故事创意"
        return normalized

    @staticmethod
    def creative_tree_to_selection(tree: Dict[str, Any]) -> str:
        if not isinstance(tree, dict):
            return ""
        lines: List[str] = []
        root = str(tree.get("label", "")).strip()
        if root:
            lines.append(f"前提：{root}")
        children = tree.get("children", [])
        if isinstance(children, list):
            for child in children[:5]:
                if not isinstance(child, dict):
                    continue
                label = str(child.get("label", "")).strip()
                description = str(child.get("description", "")).strip()
                if label and description:
                    lines.append(f"- {label}：{description}")
                elif label:
                    lines.append(f"- {label}")
        return "\n".join(lines).strip()

    @staticmethod
    def _extract_character_names(text: str, limit: int = 6) -> List[str]:
        raw = (text or "").strip()
        if not raw:
            return []

        names: List[str] = []
        # quoted names
        for match in re.findall(r"[\"'“”‘’]([A-Za-z\u4e00-\u9fff][A-Za-z0-9_\-\u4e00-\u9fff]{1,20})[\"'“”‘’]", raw):
            name = str(match).strip()
            if name and name not in names:
                names.append(name)

        # comma-separated hints
        for token in re.split(r"[,\n，、;；]", raw):
            token = token.strip()
            if len(token) < 2 or len(token) > 20:
                continue
            if re.fullmatch(r"[A-Za-z\u4e00-\u9fff][A-Za-z0-9_\-\u4e00-\u9fff]{1,20}", token) and token not in names:
                names.append(token)

        return names[:limit]

    @staticmethod
    def default_relation_graph(story_description: str = "", character_list: Optional[List[str]] = None) -> Dict[str, Any]:
        names = list(character_list or [])
        if not names:
            names = WriterSkillHelper._extract_character_names(story_description)
        if len(names) < 2:
            names = ["主角", "伙伴", "对手"]

        nodes = [{"id": name, "label": name, "group": "character"} for name in names]
        edges = []
        if len(names) >= 2:
            edges.append({"from": names[0], "to": names[1], "label": "同盟"})
        if len(names) >= 3:
            edges.append({"from": names[0], "to": names[2], "label": "冲突"})

        return {"nodes": nodes, "edges": edges}

    @staticmethod
    def normalize_relation_graph(
        payload: Dict[str, Any],
        story_description: str = "",
        character_list: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        graph = payload.get("relation_graph", payload)
        if not isinstance(graph, dict):
            return WriterSkillHelper.default_relation_graph(story_description, character_list)

        raw_nodes = graph.get("nodes", [])
        raw_edges = graph.get("edges", [])

        nodes: List[Dict[str, str]] = []
        if isinstance(raw_nodes, list):
            for node in raw_nodes[:30]:
                if not isinstance(node, dict):
                    continue
                node_id = str(node.get("id", "")).strip()
                label = str(node.get("label", node_id)).strip()
                group = str(node.get("group", "character")).strip() or "character"
                if not node_id and label:
                    node_id = label
                if node_id:
                    nodes.append({"id": node_id, "label": label or node_id, "group": group})

        existing_ids = {item["id"] for item in nodes}
        edges: List[Dict[str, str]] = []
        if isinstance(raw_edges, list):
            for edge in raw_edges[:60]:
                if not isinstance(edge, dict):
                    continue
                edge_from = str(edge.get("from", "")).strip()
                edge_to = str(edge.get("to", "")).strip()
                label = str(edge.get("label", "related")).strip() or "related"
                if edge_from and edge_to:
                    if edge_from not in existing_ids:
                        nodes.append({"id": edge_from, "label": edge_from, "group": "character"})
                        existing_ids.add(edge_from)
                    if edge_to not in existing_ids:
                        nodes.append({"id": edge_to, "label": edge_to, "group": "character"})
                        existing_ids.add(edge_to)
                    edges.append({"from": edge_from, "to": edge_to, "label": label})

        if not nodes:
            return WriterSkillHelper.default_relation_graph(story_description, character_list)
        if not edges and len(nodes) >= 2:
            edges.append({"from": nodes[0]["id"], "to": nodes[1]["id"], "label": "相关"})

        return {"nodes": nodes, "edges": edges}
