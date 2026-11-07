"""
RAG（检索增强生成）API
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, Response
from pathlib import Path
from urllib.parse import quote
from pydantic import BaseModel
from typing import List, Optional
import logging
from app.services.ragservice import RAGService
from app.services.aiservice import AIService

logger = logging.getLogger(__name__)

router = APIRouter()

# 初始化RAG服务
rag_service = RAGService()
ai_service = AIService()

class RAGQuery(BaseModel):
    """RAG查询请求"""
    query: str
    top_k: int = 5
    context_id: Optional[str] = None
    use_knowledge_graph: bool = False  # 是否使用知识图谱增强
    role_id: Optional[str] = None  # 角色ID（用于过滤知识库）

class RAGResponse(BaseModel):
    """RAG响应"""
    answer: str
    sources: List[dict]
    confidence: float

@router.post("/query", response_model=RAGResponse)
async def query_rag(request: RAGQuery):
    """
    RAG查询接口
    
    实现检索增强生成：
    1. 从知识库检索相关文档
    2. 构建增强上下文
    3. 使用AI服务生成回答
    """
    try:
        # 1. 文档检索（支持知识图谱增强）
        if request.use_knowledge_graph:
            enhanced_result = rag_service.enhanced_search(
                query=request.query,
                top_k=request.top_k,
                use_knowledge_graph=True,
                role_id=request.role_id
            )
            search_results = enhanced_result.get("fused_results", enhanced_result.get("vector_results", []))
            kg_info = {
                "use_kg": True,
                "entities": enhanced_result.get("entities", []),
                "kg_results": enhanced_result.get("kg_results", [])
            }
        else:
            search_results = rag_service.search(
                query=request.query,
                top_k=request.top_k,
                context_id=request.context_id,
                role_id=request.role_id
            )
            kg_info = {"use_kg": False}
        
        # 2. 构建增强上下文
        context = rag_service.build_context(request.query, search_results)
        
        # 3. 使用AI服务生成回答（结合检索结果）
        enhanced_query = f"{request.query}\n\n{context}" if context else request.query
        
        ai_response = await ai_service.generate_text(
            text=enhanced_query,
            context=None  # 可以传入对话历史
        )
        
        # 构建来源信息
        sources = [
            {
                "doc_id": result.get("doc_id"),
                "filename": result.get("filename"),
                "score": result.get("score", 0.0),
                "excerpt": result.get("content", "")[:200]
            }
            for result in search_results
        ]
        
        response = RAGResponse(
            answer=ai_response.get("text", ""),
            sources=sources,
            confidence=ai_response.get("confidence", 0.85)
        )
        
        # 添加知识图谱信息（如果使用）
        if request.use_knowledge_graph:
            response_dict = response.dict()
            response_dict["kg_info"] = kg_info
            return response_dict
        
        return response
    except Exception as e:
        logger.error(f"RAG查询失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"RAG查询失败: {str(e)}")

@router.post("/documents")
async def upload_document(
    file: UploadFile = File(...),
    metadata: Optional[str] = Form(None),
    role_id: Optional[str] = Form(None)
):
    """
    上传文档到知识库
    
    支持格式：txt, md, pdf, doc, docx等
    文档会被解析、分块并建立索引
    
    参数：
    - role_id: 角色ID，用于将文档分类到特定角色的知识库
    """
    try:
        # 读取文件数据
        file_data = await file.read()
        
        # 解析元数据（如果提供）
        doc_metadata = {}
        if metadata:
            try:
                import json
                doc_metadata = json.loads(metadata)
            except:
                pass
        
        # 上传并处理文档
        doc_id = rag_service.upload_document(
            file_data=file_data,
            filename=file.filename or "unknown",
            metadata=doc_metadata,
            role_id=role_id
        )
        
        return {
            "message": "文档上传成功",
            "document_id": doc_id,
            "filename": file.filename
        }
    except Exception as e:
        logger.error(f"文档上传失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"文档上传失败: {str(e)}")

@router.get("/documents")
async def list_documents(role_id: Optional[str] = None):
    """
    列出已上传的文档
    
    参数：
    - role_id: 角色ID，如果提供则只返回该角色的文档
    """
    try:
        documents = []
        for doc_id, doc_data in rag_service.documents.items():
            # 如果指定了role_id，只返回匹配的文档
            if role_id and doc_data.get("role_id") != role_id:
                continue
            documents.append({
                "doc_id": doc_id,
                "filename": doc_data.get("filename", ""),
                "upload_time": doc_data.get("upload_time", ""),
                "role_id": doc_data.get("role_id"),
                "metadata": doc_data.get("metadata", {})
            })
        return {"documents": documents, "count": len(documents)}
    except Exception as e:
        logger.error(f"获取文档列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/documents/{doc_id}/download")
async def download_document(doc_id: str):
    document = rag_service.documents.get(doc_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    filename = str(document.get("filename") or "document").replace("\\", "/").rsplit("/", 1)[-1]
    original = rag_service.original_document_path(doc_id)
    if original is not None:
        return FileResponse(original, filename=filename, media_type="application/octet-stream",
                            headers={"X-RAG-Download-Source": "original"})
    # Before original files were retained, only the extracted text was persisted.
    # Return that full text honestly; never manufacture a PDF or DOCX container.
    text = document.get("text")
    if not isinstance(text, str):
        raise HTTPException(status_code=404, detail="文档原始文件与提取文本均不可用")
    text_filename = filename if Path(filename).suffix.lower() in {".txt", ".md"} else f"{filename}.txt"
    return Response(text.encode("utf-8"), media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(text_filename, safe='')}",
                             "X-RAG-Download-Source": "extracted-text"})


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    """
    删除指定文档
    """
    try:
        if doc_id in rag_service.documents:
            original = rag_service.original_document_path(doc_id)
            del rag_service.documents[doc_id]
            rag_service._rebuild_index()
            rag_service._save_documents()
            if original is not None:
                original.unlink(missing_ok=True)
            return {"message": "文档删除成功", "doc_id": doc_id}
        else:
            raise HTTPException(status_code=404, detail="文档不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除文档失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

