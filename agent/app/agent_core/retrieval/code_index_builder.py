import ast
import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.agent_core.retrieval.chroma_client import chroma_client

logger = logging.getLogger(__name__)


class CodeIndexBuilder:
    CODE_COLLECTION = "code_index"

    def __init__(self):
        self.app_dir = Path(__file__).resolve().parents[2]
        self.agent_dir = Path(__file__).resolve().parents[3]
        self.project_root = Path(__file__).resolve().parents[4]
        self.cache_dir = self.app_dir / "data" / "code_index"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.manifest_path = self.cache_dir / "code_index_manifest.json"
        self.cache_path = self.cache_dir / "code_index_cache.json"

        self.source_extensions = {
            ".py",
            ".java",
            ".js",
            ".jsx",
            ".ts",
            ".tsx",
            ".vue",
            ".go",
            ".rs",
            ".kt",
            ".swift",
            ".c",
            ".cc",
            ".cpp",
            ".h",
            ".hpp",
        }
        self.skip_dirs = {
            ".git",
            ".idea",
            ".vscode",
            "__pycache__",
            "node_modules",
            "dist",
            "build",
            "target",
            ".venv",
            "venv",
            ".mypy_cache",
            ".pytest_cache",
        }

    def _normalize_path(self, root_path: Optional[str]) -> Path:
        if root_path:
            root = Path(root_path)
            if not root.is_absolute():
                root = (self.project_root / root).resolve()
            return root

        env_root = os.getenv("AGENT_CODE_INDEX_ROOT", "").strip()
        if env_root:
            env_path = Path(env_root)
            if not env_path.is_absolute():
                env_path = (self.project_root / env_path).resolve()
            return env_path

        return (self.project_root / "backend" / "src").resolve()

    def _load_json(self, path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
        if not path.exists():
            return dict(default)
        try:
            raw = path.read_text(encoding="utf-8")
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else dict(default)
        except Exception:
            return dict(default)

    def _save_json(self, path: Path, payload: Dict[str, Any]) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to save json %s: %s", path, exc)

    def _detect_language(self, file_path: Path) -> str:
        suffix = file_path.suffix.lower()
        mapping = {
            ".py": "python",
            ".java": "java",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".vue": "vue",
            ".go": "go",
            ".rs": "rust",
            ".kt": "kotlin",
            ".swift": "swift",
            ".c": "c",
            ".cc": "cpp",
            ".cpp": "cpp",
            ".h": "c",
            ".hpp": "cpp",
        }
        return mapping.get(suffix, suffix.lstrip(".") or "text")

    def _is_source_file(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self.source_extensions

    def _iter_source_files(self, root_path: Path) -> List[Path]:
        if not root_path.exists() or not root_path.is_dir():
            return []

        files: List[Path] = []
        for current_root, dirs, filenames in os.walk(root_path):
            dirs[:] = [item for item in dirs if item not in self.skip_dirs]
            current_root_path = Path(current_root)
            for filename in filenames:
                file_path = current_root_path / filename
                if self._is_source_file(file_path):
                    files.append(file_path)
        return files

    def _file_hash(self, file_path: Path) -> str:
        hasher = hashlib.sha1()
        try:
            with file_path.open("rb") as stream:
                while True:
                    block = stream.read(1024 * 64)
                    if not block:
                        break
                    hasher.update(block)
            return hasher.hexdigest()
        except Exception:
            return ""

    def _extract_source_snippet(self, lines: List[str], line_no: int, max_lines: int = 25) -> str:
        if not lines:
            return ""
        start = max(0, line_no - 1)
        end = min(len(lines), start + max_lines)
        snippet = "".join(lines[start:end]).strip()
        return snippet[:4000]

    def _parse_python_symbols(self, text: str) -> List[Dict[str, Any]]:
        symbols: List[Dict[str, Any]] = []
        try:
            tree = ast.parse(text)
        except Exception:
            return symbols

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                symbols.append(
                    {
                        "type": "class",
                        "name": node.name,
                        "line": int(getattr(node, "lineno", 1)),
                        "class_name": node.name,
                        "function_name": None,
                        "docstring": ast.get_docstring(node) or "",
                    }
                )
            elif isinstance(node, ast.FunctionDef):
                symbols.append(
                    {
                        "type": "function",
                        "name": node.name,
                        "line": int(getattr(node, "lineno", 1)),
                        "class_name": None,
                        "function_name": node.name,
                        "docstring": ast.get_docstring(node) or "",
                    }
                )
            elif isinstance(node, ast.AsyncFunctionDef):
                symbols.append(
                    {
                        "type": "function",
                        "name": node.name,
                        "line": int(getattr(node, "lineno", 1)),
                        "class_name": None,
                        "function_name": node.name,
                        "docstring": ast.get_docstring(node) or "",
                    }
                )
        return symbols

    def _parse_java_symbols(self, lines: List[str]) -> List[Dict[str, Any]]:
        symbols: List[Dict[str, Any]] = []
        class_pattern = re.compile(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)")
        method_pattern = re.compile(
            r"(public|private|protected)\s+"
            r"(static\s+)?([\w<>\[\], ?]+)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)"
        )
        current_class = None
        for index, raw in enumerate(lines, start=1):
            line = raw.strip()
            class_match = class_pattern.search(line)
            if class_match:
                current_class = class_match.group(1)
                symbols.append(
                    {
                        "type": "class",
                        "name": current_class,
                        "line": index,
                        "class_name": current_class,
                        "function_name": None,
                        "docstring": "",
                    }
                )

            method_match = method_pattern.search(line)
            if method_match:
                method_name = method_match.group(4)
                signature = line
                symbols.append(
                    {
                        "type": "function",
                        "name": method_name,
                        "line": index,
                        "class_name": current_class,
                        "function_name": method_name,
                        "docstring": "",
                        "signature": signature[:400],
                    }
                )
        return symbols

    def _parse_js_ts_symbols(self, lines: List[str]) -> List[Dict[str, Any]]:
        symbols: List[Dict[str, Any]] = []
        class_pattern = re.compile(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)")
        function_pattern = re.compile(r"\bfunction\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")
        arrow_pattern = re.compile(
            r"\b(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>"
        )
        method_pattern = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\([^)]*\)\s*\{")

        current_class = None
        for index, raw in enumerate(lines, start=1):
            line = raw.rstrip("\n")

            class_match = class_pattern.search(line)
            if class_match:
                current_class = class_match.group(1)
                symbols.append(
                    {
                        "type": "class",
                        "name": current_class,
                        "line": index,
                        "class_name": current_class,
                        "function_name": None,
                        "docstring": "",
                    }
                )

            function_match = function_pattern.search(line)
            if function_match:
                func_name = function_match.group(1)
                symbols.append(
                    {
                        "type": "function",
                        "name": func_name,
                        "line": index,
                        "class_name": current_class,
                        "function_name": func_name,
                        "docstring": "",
                    }
                )
                continue

            arrow_match = arrow_pattern.search(line)
            if arrow_match:
                func_name = arrow_match.group(1)
                symbols.append(
                    {
                        "type": "function",
                        "name": func_name,
                        "line": index,
                        "class_name": current_class,
                        "function_name": func_name,
                        "docstring": "",
                    }
                )
                continue

            method_match = method_pattern.search(line)
            if method_match and current_class:
                method_name = method_match.group(1)
                if method_name not in {"if", "for", "while", "switch", "catch"}:
                    symbols.append(
                        {
                            "type": "function",
                            "name": method_name,
                            "line": index,
                            "class_name": current_class,
                            "function_name": method_name,
                            "docstring": "",
                        }
                    )
        return symbols

    def _extract_symbols(self, file_path: Path, text: str) -> List[Dict[str, Any]]:
        language = self._detect_language(file_path)
        lines = text.splitlines(keepends=True)
        if language == "python":
            return self._parse_python_symbols(text)
        if language == "java":
            return self._parse_java_symbols(lines)
        if language in {"javascript", "typescript", "vue"}:
            if language == "vue":
                script_blocks = re.findall(r"<script[^>]*>([\s\S]*?)</script>", text, flags=re.IGNORECASE)
                script_text = "\n".join(script_blocks) if script_blocks else text
                return self._parse_js_ts_symbols(script_text.splitlines(keepends=True))
            return self._parse_js_ts_symbols(lines)
        return []

    def _build_documents_for_file(self, root_path: Path, file_path: Path) -> List[Dict[str, Any]]:
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return []

        language = self._detect_language(file_path)
        rel_path = file_path.relative_to(root_path).as_posix()
        lines = text.splitlines(keepends=True)
        symbols = self._extract_symbols(file_path, text)

        docs: List[Dict[str, Any]] = []
        used_ids = set()

        def add_doc(symbol_name: str, line_no: int, function_name: Optional[str], class_name: Optional[str], docstring: str) -> None:
            base_id = f"{rel_path}:{symbol_name}:{line_no}"
            doc_id = base_id
            suffix = 1
            while doc_id in used_ids:
                suffix += 1
                doc_id = f"{base_id}:{suffix}"
            used_ids.add(doc_id)

            snippet = self._extract_source_snippet(lines, line_no)
            if not snippet:
                return

            metadata = {
                "file_path": rel_path,
                "function_name": function_name,
                "class_name": class_name,
                "language": language,
                "docstring": (docstring or "")[:500],
                "line": int(line_no),
            }
            docs.append({"id": doc_id, "text": snippet, "metadata": metadata})

        if symbols:
            for symbol in symbols:
                symbol_name = str(symbol.get("name", "symbol")).strip() or "symbol"
                line_no = int(symbol.get("line", 1))
                add_doc(
                    symbol_name=symbol_name,
                    line_no=line_no,
                    function_name=symbol.get("function_name"),
                    class_name=symbol.get("class_name"),
                    docstring=str(symbol.get("docstring", "")),
                )
        else:
            add_doc(
                symbol_name="file",
                line_no=1,
                function_name=None,
                class_name=None,
                docstring="",
            )
        return docs

    def _delete_ids(self, ids: List[str]) -> None:
        if not ids or not chroma_client.is_available():
            return
        try:
            collection = chroma_client.get_or_create_collection(self.CODE_COLLECTION)
            if collection is None:
                return
            collection.delete(ids=ids)
        except Exception as exc:
            logger.warning("Failed to delete stale code index ids: %s", exc)

    def _keyword_score(self, text: str, tokens: List[str]) -> float:
        if not text:
            return 0.0
        lowered = text.lower()
        hits = sum(1 for token in tokens if token and token in lowered)
        if not tokens:
            return 0.0
        return float(hits) / float(len(tokens))

    def _tokenize(self, text: str) -> List[str]:
        tokens = re.findall(r"[a-z0-9_./-]+|[\u4e00-\u9fff]+", (text or "").lower())
        return [token for token in tokens if token]

    def build_code_index(self, root_path: Optional[str] = None) -> Dict[str, Any]:
        root = self._normalize_path(root_path)
        if not root.exists():
            return {
                "success": False,
                "root_path": str(root),
                "indexed_files": 0,
                "indexed_docs": 0,
                "message": "root path does not exist",
            }

        manifest = self._load_json(
            self.manifest_path,
            default={"root_path": "", "files": {}, "updated_at": 0},
        )
        old_files = manifest.get("files", {})
        if not isinstance(old_files, dict):
            old_files = {}

        source_files = self._iter_source_files(root)
        current_rel_paths = {path.relative_to(root).as_posix() for path in source_files}

        upsert_docs: List[Dict[str, Any]] = []
        updated_files: Dict[str, Dict[str, Any]] = {}
        delete_ids: List[str] = []
        delete_doc_keys: List[str] = []
        cache_docs = self._load_json(self.cache_path, default={"docs": {}})
        docs_cache = cache_docs.get("docs", {})
        if not isinstance(docs_cache, dict):
            docs_cache = {}

        indexed_files = 0
        for file_path in source_files:
            rel_path = file_path.relative_to(root).as_posix()
            stat = file_path.stat()
            mtime = float(stat.st_mtime)
            file_hash = self._file_hash(file_path)

            previous = old_files.get(rel_path, {})
            previous_hash = str(previous.get("hash", ""))
            previous_mtime = float(previous.get("mtime", 0.0) or 0.0)
            previous_ids = list(previous.get("ids", [])) if isinstance(previous.get("ids", []), list) else []

            changed = (file_hash != previous_hash) or (abs(mtime - previous_mtime) > 1e-6)
            if changed:
                docs = self._build_documents_for_file(root, file_path)
                doc_ids = [doc["id"] for doc in docs]
                stale_ids = [item for item in previous_ids if item not in doc_ids]
                if stale_ids:
                    delete_ids.extend(stale_ids)
                    delete_doc_keys.extend(stale_ids)

                upsert_docs.extend(docs)
                for doc in docs:
                    docs_cache[doc["id"]] = {"content": doc["text"], "metadata": doc["metadata"]}
                indexed_files += 1
            else:
                doc_ids = previous_ids

            updated_files[rel_path] = {
                "mtime": mtime,
                "hash": file_hash,
                "ids": doc_ids,
                "size": int(stat.st_size),
            }

        removed_files = [path for path in old_files.keys() if path not in current_rel_paths]
        for removed in removed_files:
            previous = old_files.get(removed, {})
            previous_ids = previous.get("ids", [])
            if isinstance(previous_ids, list):
                delete_ids.extend(previous_ids)
                delete_doc_keys.extend(previous_ids)

        for doc_key in delete_doc_keys:
            docs_cache.pop(doc_key, None)

        if upsert_docs and chroma_client.is_available():
            chroma_client.add_documents(self.CODE_COLLECTION, upsert_docs)
        if delete_ids:
            self._delete_ids(delete_ids)

        new_manifest = {
            "root_path": str(root),
            "files": updated_files,
            "updated_at": int(time.time()),
        }
        self._save_json(self.manifest_path, new_manifest)
        self._save_json(self.cache_path, {"docs": docs_cache})

        return {
            "success": True,
            "root_path": str(root),
            "indexed_files": indexed_files,
            "indexed_docs": len(upsert_docs),
            "deleted_docs": len(delete_ids),
            "total_files": len(updated_files),
            "vector_enabled": chroma_client.is_available(),
        }

    def search_code(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if chroma_client.is_available():
            try:
                rows = chroma_client.query(self.CODE_COLLECTION, query_text=query, top_k=top_k)
                if rows:
                    return rows
            except Exception as exc:
                logger.warning("Vector code search failed, fallback to keyword: %s", exc)

        cache_data = self._load_json(self.cache_path, default={"docs": {}})
        docs = cache_data.get("docs", {})
        if not isinstance(docs, dict) or not docs:
            return []

        tokens = self._tokenize(query)
        scored: List[Tuple[str, float, Dict[str, Any]]] = []
        for doc_id, payload in docs.items():
            if not isinstance(payload, dict):
                continue
            content = str(payload.get("content", ""))
            score = self._keyword_score(content, tokens)
            if score <= 0:
                continue
            metadata = payload.get("metadata", {})
            scored.append((doc_id, score, {"content": content, "metadata": metadata}))

        scored.sort(key=lambda item: item[1], reverse=True)
        results: List[Dict[str, Any]] = []
        for doc_id, score, payload in scored[: max(1, top_k)]:
            results.append(
                {
                    "id": doc_id,
                    "content": payload.get("content", ""),
                    "metadata": payload.get("metadata", {}),
                    "score": round(float(score), 4),
                }
            )
        return results


code_index_builder = CodeIndexBuilder()


def build_code_index(root_path: Optional[str] = None) -> Dict[str, Any]:
    return code_index_builder.build_code_index(root_path=root_path)


def search_code(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    return code_index_builder.search_code(query=query, top_k=top_k)
