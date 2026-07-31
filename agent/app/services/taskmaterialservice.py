"""Persistent, owner-scoped source materials for AgentOS workflows."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.paths import APP_DATA_DIR
from app.security.internal_auth import current_trusted_user
from app.services.multimodalservice import multimodal_fusion_service


MAX_MATERIAL_BYTES = 10 * 1024 * 1024
MAX_OCR_PAGES = 50
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
_MATERIAL_ID = re.compile(r"^mat_[0-9a-f]{32}$")
_PLACEHOLDER_MARKERS = ("需要安装", "需要配置API密钥", "OCR识别失败")


class MaterialError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _owner() -> dict[str, str]:
    actor = current_trusted_user()
    if actor is None:
        return {"userId": "anonymous", "tenantId": "default"}
    return {"userId": actor.user_id, "tenantId": actor.tenant_id or "default"}


class TaskMaterialStore:
    """File-backed metadata store; source files never leave the Agent data volume."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (APP_DATA_DIR / "task-materials")
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def create(self, *, filename: str, media_type: str, content: bytes, extraction: dict[str, Any]) -> dict[str, Any]:
        owner = _owner()
        material_id = f"mat_{uuid.uuid4().hex}"
        material_dir = self.root / material_id
        material_dir.mkdir(parents=False, exist_ok=False)
        extension = Path(filename).suffix.lower()
        source_name = f"source{extension}"
        created_at = _now()
        text = str(extraction["text"])
        metadata = {
            "materialId": material_id,
            "state": "ready",
            "owner": owner,
            "originalFilename": filename.replace("\\", "/").rsplit("/", 1)[-1],
            "mediaType": media_type or "application/octet-stream",
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "extractedTextSha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "textLength": len(text),
            "sourceFile": source_name,
            "extraction": {key: value for key, value in extraction.items() if key != "text"},
            "createdAt": created_at.isoformat(),
            "updatedAt": created_at.isoformat(),
            "bindings": [],
        }
        try:
            self._atomic_write_bytes(material_dir / source_name, content)
            self._atomic_write_text(material_dir / "extracted.txt", text)
            self._write_metadata(material_dir, metadata)
        except Exception:
            shutil.rmtree(material_dir, ignore_errors=True)
            raise
        return {**metadata, "extractedText": text}

    def get(self, material_id: str, *, include_text: bool = False) -> dict[str, Any]:
        material_dir = self._directory(material_id)
        with self._lock:
            metadata = self._read_metadata(material_dir)
            self._require_owner(metadata)
            result = dict(metadata)
            if include_text:
                result["extractedText"] = (material_dir / "extracted.txt").read_text(encoding="utf-8")
            return result

    def bind(self, material_id: str, *, task_id: str, run_id: str) -> dict[str, Any]:
        material_dir = self._directory(material_id)
        with self._lock:
            metadata = self._read_metadata(material_dir)
            self._require_owner(metadata)
            binding = {"taskId": task_id, "runId": run_id}
            if binding not in metadata["bindings"]:
                metadata["bindings"].append(binding)
            metadata["state"] = "bound"
            metadata["updatedAt"] = _now().isoformat()
            self._write_metadata(material_dir, metadata)
            return dict(metadata)

    def delete_draft(self, material_id: str) -> None:
        material_dir = self._directory(material_id)
        with self._lock:
            metadata = self._read_metadata(material_dir)
            self._require_owner(metadata)
            if metadata.get("bindings"):
                raise MaterialError("MATERIAL_ALREADY_BOUND", "已绑定运行的材料不能作为草稿删除", status_code=409)
            shutil.rmtree(material_dir)

    def release_run(self, run_id: str, material_ids: list[str]) -> None:
        for material_id in material_ids:
            try:
                material_dir = self._directory(material_id)
                with self._lock:
                    metadata = self._read_metadata(material_dir)
                    metadata["bindings"] = [
                        item for item in metadata.get("bindings", []) if item.get("runId") != run_id
                    ]
                    metadata["state"] = "bound" if metadata["bindings"] else "ready"
                    metadata["updatedAt"] = _now().isoformat()
                    self._write_metadata(material_dir, metadata)
            except (FileNotFoundError, MaterialError):
                continue

    def cleanup_drafts(self, *, older_than: timedelta = timedelta(hours=24)) -> int:
        cutoff = _now() - older_than
        removed = 0
        for material_dir in self.root.glob("mat_*"):
            try:
                metadata = self._read_metadata(material_dir)
                created_at = datetime.fromisoformat(metadata["createdAt"])
                if not metadata.get("bindings") and created_at < cutoff:
                    shutil.rmtree(material_dir)
                    removed += 1
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                continue
        return removed

    def _directory(self, material_id: str) -> Path:
        if not _MATERIAL_ID.fullmatch(material_id or ""):
            raise MaterialError("MATERIAL_NOT_FOUND", "任务材料不存在", status_code=404)
        material_dir = self.root / material_id
        if not material_dir.is_dir():
            raise MaterialError("MATERIAL_NOT_FOUND", "任务材料不存在", status_code=404)
        return material_dir

    def _require_owner(self, metadata: dict[str, Any]) -> None:
        if metadata.get("owner") != _owner():
            raise MaterialError("MATERIAL_NOT_FOUND", "任务材料不存在", status_code=404)

    def _read_metadata(self, material_dir: Path) -> dict[str, Any]:
        return json.loads((material_dir / "metadata.json").read_text(encoding="utf-8"))

    def _write_metadata(self, material_dir: Path, metadata: dict[str, Any]) -> None:
        self._atomic_write_text(
            material_dir / "metadata.json",
            json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        )

    @staticmethod
    def _atomic_write_text(path: Path, value: str) -> None:
        TaskMaterialStore._atomic_write_bytes(path, value.encode("utf-8"))

    @staticmethod
    def _atomic_write_bytes(path: Path, value: bytes) -> None:
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_bytes(value)
        os.replace(temporary, path)


async def extract_material(content: bytes, filename: str) -> dict[str, Any]:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise MaterialError("MATERIAL_TYPE_UNSUPPORTED", "仅支持 PDF、DOCX、TXT、MD 格式", status_code=415)
    if not content:
        raise MaterialError("MATERIAL_EMPTY", "文件内容为空", status_code=400)
    if len(content) > MAX_MATERIAL_BYTES:
        raise MaterialError("MATERIAL_TOO_LARGE", "文件不能超过 10MB", status_code=413)
    if extension == ".pdf" and not content.startswith(b"%PDF"):
        raise MaterialError("MATERIAL_CONTENT_INVALID", "PDF 文件内容与扩展名不匹配", status_code=415)
    if extension == ".docx" and not content.startswith(b"PK"):
        raise MaterialError("MATERIAL_CONTENT_INVALID", "DOCX 文件内容与扩展名不匹配", status_code=415)

    result = multimodal_fusion_service.document_processor.process_document(content, filename, True)
    text = str(result.get("text") or "").strip()
    if result.get("type") == "error" or any(marker in text for marker in _PLACEHOLDER_MARKERS):
        text = ""

    metadata = dict(result.get("metadata") or {})
    pages = int(metadata.get("pages") or 0)
    ocr_used = False
    method = str(metadata.get("method") or metadata.get("encoding") or extension.lstrip("."))
    if extension == ".pdf" and len(text) < 20:
        text, pages = await _ocr_pdf(content)
        method = "pymupdf+qwen-vl-ocr"
        ocr_used = True
    if not text:
        message = str(result.get("content") or result.get("note") or "未能从文件中提取到有效正文")
        raise MaterialError("MATERIAL_TEXT_EMPTY", message, status_code=422)
    return {"text": text, "method": method, "ocrUsed": ocr_used, "pages": pages}


async def _ocr_pdf(content: bytes) -> tuple[str, int]:
    try:
        import fitz
    except ImportError as exc:
        raise MaterialError("MATERIAL_OCR_UNAVAILABLE", "扫描 PDF 需要安装 PyMuPDF", status_code=503) from exc
    try:
        document = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise MaterialError("MATERIAL_CONTENT_INVALID", "PDF 文件已损坏或无法读取", status_code=422) from exc
    try:
        if document.page_count > MAX_OCR_PAGES:
            raise MaterialError("MATERIAL_OCR_PAGE_LIMIT", "扫描 PDF 不能超过 50 页，请拆分后重试", status_code=422)
        parts: list[str] = []
        for page in document:
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            result = await multimodal_fusion_service.image_processor.process_image(pixmap.tobytes("png"), task="ocr")
            page_text = str(result.get("content") or "").strip()
            if not result.get("success") or not page_text or any(marker in page_text for marker in _PLACEHOLDER_MARKERS):
                raise MaterialError(
                    "MATERIAL_OCR_UNAVAILABLE",
                    str(result.get("note") or "扫描 PDF OCR 服务不可用"),
                    status_code=503,
                )
            parts.append(page_text)
        text = "\n\n".join(parts).strip()
        if not text:
            raise MaterialError("MATERIAL_TEXT_EMPTY", "扫描 PDF 未识别出有效正文", status_code=422)
        return text, document.page_count
    finally:
        document.close()


task_material_store = TaskMaterialStore()
