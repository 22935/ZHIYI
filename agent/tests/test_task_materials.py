import asyncio
import hashlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import taskmaterialservice as materials
from app.api import agentos_core


def test_text_material_is_persisted_bound_and_released(tmp_path):
    content = "甲方应当在验收后十日内付款。".encode("utf-8")
    extraction = asyncio.run(materials.extract_material(content, "合同.md"))
    store = materials.TaskMaterialStore(tmp_path)

    created = store.create(
        filename="合同.md",
        media_type="text/markdown",
        content=content,
        extraction=extraction,
    )

    assert created["state"] == "ready"
    assert created["sha256"] == hashlib.sha256(content).hexdigest()
    assert created["extractedText"] == content.decode()
    bound = store.bind(created["materialId"], task_id="task_1", run_id="run_1")
    assert bound["state"] == "bound"
    with pytest.raises(materials.MaterialError, match="不能作为草稿删除"):
        store.delete_draft(created["materialId"])

    store.release_run("run_1", [created["materialId"]])
    released = store.get(created["materialId"])
    assert released["state"] == "ready"
    assert released["bindings"] == []
    assert (tmp_path / created["materialId"] / released["sourceFile"]).read_bytes() == content


def test_rejects_empty_unsupported_and_forged_files():
    with pytest.raises(materials.MaterialError) as empty:
        asyncio.run(materials.extract_material(b"", "合同.txt"))
    assert empty.value.status_code == 400

    with pytest.raises(materials.MaterialError) as unsupported:
        asyncio.run(materials.extract_material(b"hello", "合同.exe"))
    assert unsupported.value.status_code == 415

    with pytest.raises(materials.MaterialError) as forged:
        asyncio.run(materials.extract_material(b"not a pdf", "合同.pdf"))
    assert forged.value.code == "MATERIAL_CONTENT_INVALID"


def test_scanned_pdf_uses_ocr_and_rejects_placeholder(monkeypatch):
    monkeypatch.setattr(
        materials.multimodal_fusion_service.document_processor,
        "process_document",
        lambda *_args, **_kwargs: {"type": "pdf", "text": "", "metadata": {"pages": 1}},
    )

    async def successful_ocr(_content):
        return "OCR 合同正文", 1

    monkeypatch.setattr(materials, "_ocr_pdf", successful_ocr)
    result = asyncio.run(materials.extract_material(b"%PDF-scanned", "scan.pdf"))
    assert result["ocrUsed"] is True
    assert result["text"] == "OCR 合同正文"

    async def unavailable_ocr(_content):
        raise materials.MaterialError("MATERIAL_OCR_UNAVAILABLE", "OCR unavailable", status_code=503)

    monkeypatch.setattr(materials, "_ocr_pdf", unavailable_ocr)
    with pytest.raises(materials.MaterialError) as unavailable:
        asyncio.run(materials.extract_material(b"%PDF-scanned", "scan.pdf"))
    assert unavailable.value.status_code == 503


def test_workflow_input_resolves_canonical_material_metadata(tmp_path, monkeypatch):
    store = materials.TaskMaterialStore(tmp_path)
    content = "原始合同正文".encode("utf-8")
    created = store.create(
        filename="合同.txt",
        media_type="text/plain",
        content=content,
        extraction={"text": "原始合同正文", "method": "utf-8", "ocrUsed": False, "pages": 0},
    )
    monkeypatch.setattr(agentos_core, "task_material_store", store)
    request = agentos_core.WorkflowStartRequest(
        title="合同审查",
        input={
            "contractText": "人工修订后的合同正文",
            "sourceMaterials": [{"materialId": created["materialId"], "purpose": "contract"}],
        },
    )

    resolved = agentos_core._resolve_source_materials(request)
    reference = resolved.input["sourceMaterials"][0]

    assert resolved.input["contractText"] == "人工修订后的合同正文"
    assert reference["edited"] is True
    assert reference["sha256"] == created["sha256"]
    assert reference["uri"] == f"material://{created['materialId']}"


def test_material_api_accepts_real_multipart_and_deletes_draft(tmp_path, monkeypatch):
    store = materials.TaskMaterialStore(tmp_path)
    monkeypatch.setattr(agentos_core, "task_material_store", store)
    app = FastAPI()
    app.include_router(agentos_core.create_router(agentos_core.runtime, agentos_core.coordinator))
    client = TestClient(app)

    uploaded = client.post(
        "/core/materials",
        files={"file": ("contract.md", "合同正文", "text/markdown")},
    )

    assert uploaded.status_code == 201
    payload = uploaded.json()
    assert payload["state"] == "ready"
    assert payload["extractedText"] == "合同正文"
    removed = client.delete(f"/core/materials/{payload['materialId']}")
    assert removed.status_code == 204
