from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import rag
from app.services.ragservice import RAGService


def client_for(monkeypatch, service):
    monkeypatch.setattr(rag, "rag_service", service)
    app = FastAPI()
    app.include_router(rag.router, prefix="/rag")
    return TestClient(app)


def test_uploaded_original_bytes_survive_service_restart_and_download(tmp_path, monkeypatch):
    service = RAGService(str(tmp_path))
    payload = "完整原文\r\n第二行\n".encode("utf-8")
    document_id = service.upload_document(payload, "知识文档.txt")
    reloaded = RAGService(str(tmp_path))
    response = client_for(monkeypatch, reloaded).get(f"/rag/documents/{document_id}/download")
    assert response.status_code == 200
    assert response.content == payload
    assert response.headers["x-rag-download-source"] == "original"
    assert quote("知识文档.txt") in response.headers["content-disposition"]


def test_historical_documents_export_full_text_with_honest_filename(tmp_path, monkeypatch):
    service = RAGService(str(tmp_path))
    text = "历史提取文本\n" * 5000
    service.documents["historical"] = {"filename": "旧合同.pdf", "text": text}
    response = client_for(monkeypatch, service).get("/rag/documents/historical/download")
    assert response.status_code == 200
    assert response.content == text.encode("utf-8")
    assert response.headers["x-rag-download-source"] == "extracted-text"
    assert quote("旧合同.pdf.txt") in response.headers["content-disposition"]
    assert not (tmp_path / "originals").exists()


def test_download_requires_document_and_delete_removes_only_its_original(tmp_path, monkeypatch):
    service = RAGService(str(tmp_path))
    first = service.upload_document(b"first document", "first.txt")
    second = service.upload_document(b"second document", "second.txt")
    original = service.original_document_path(first)
    other = service.original_document_path(second)
    assert original is not None and other is not None
    client = client_for(monkeypatch, service)
    assert client.get("/rag/documents/missing/download").status_code == 404
    assert client.delete(f"/rag/documents/{first}").status_code == 200
    assert not original.exists()
    assert other.read_bytes() == b"second document"
    assert client.get(f"/rag/documents/{first}/download").status_code == 404
    assert service.original_document_path("../documents.json") is None
    assert (Path(tmp_path) / "documents.json").is_file()
