"""
知识图谱API路由
"""
import logging
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Dict, List, Optional
from app.services.knowledgegraphservice import knowledge_graph_service
from app.services.ragservice import RAGService

router = APIRouter()
logger = logging.getLogger(__name__)


class BuildGraphRequest(BaseModel):
    documents: List[Dict]  # [{doc_id, text, metadata}]
    role_id: Optional[str] = None  # 角色ID（用于分类知识图谱）


class HybridSearchRequest(BaseModel):
    question: str
    vector_db_results: List[Dict]
    top_k: int = 5


class ReasonRequest(BaseModel):
    question: str


def _ensure_knowledge_graph_built(role_id: Optional[str] = None):
    """Lazily build the graph from persisted RAG documents when needed."""
    rag_service = RAGService()
    candidate_documents = []

    for doc in rag_service.documents.values():
        doc_role_id = doc.get("role_id") or doc.get("metadata", {}).get("role_id")
        if role_id and doc_role_id != role_id:
            continue
        doc_id = doc.get("doc_id")
        if doc_id and doc_id in knowledge_graph_service.indexed_doc_ids:
            continue
        candidate_documents.append(doc)

    if candidate_documents:
        knowledge_graph_service.build_from_documents(candidate_documents, role_id)


@router.post("/knowledge-graph/build")
async def build_knowledge_graph(request: BuildGraphRequest):
    """
    从文档构建知识图谱
    
    示例：
    {
        "documents": [
            {
                "doc_id": "doc1",
                "text": "张三是一名律师，属于ABC律师事务所...",
                "metadata": {}
            }
        ]
    }
    """
    try:
        knowledge_graph_service.build_from_documents(request.documents, request.role_id)
        
        # 获取图谱统计信息
        kg = knowledge_graph_service.kg
        stats = {
            "entities_count": len(kg.entities),
            "triples_count": len(kg.triples),
            "relations_count": len(kg.relations)
        }
        
        return {
            "success": True,
            "message": "知识图谱构建成功",
            "data": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"知识图谱构建失败: {str(e)}")


@router.post("/knowledge-graph/search")
async def hybrid_search(request: HybridSearchRequest):
    """
    混合检索：知识图谱 + 向量数据库
    
    示例：
    {
        "question": "ABC律师事务所的律师有哪些？",
        "vector_db_results": [...],
        "top_k": 5
    }
    """
    try:
        _ensure_knowledge_graph_built()
        result = knowledge_graph_service.hybrid_retrieval(
            question=request.question,
            vector_db_results=request.vector_db_results,
            top_k=request.top_k
        )
        
        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"混合检索失败: {str(e)}")


@router.post("/knowledge-graph/reason")
async def reason_with_kg(request: ReasonRequest):
    """
    基于知识图谱进行推理
    
    示例：
    {
        "question": "张三和李四的关系是什么？"
    }
    """
    try:
        _ensure_knowledge_graph_built()
        result = knowledge_graph_service.reason_with_kg(request.question)
        
        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"知识推理失败: {str(e)}")


@router.get("/knowledge-graph/stats")
async def get_graph_stats():
    """获取知识图谱统计信息"""
    try:
        _ensure_knowledge_graph_built()
        kg = knowledge_graph_service.kg
        stats = {
            "entities_count": len(kg.entities),
            "triples_count": len(kg.triples),
            "relations_count": len(kg.relations),
            "entities": list(kg.entities.keys())[:10]  # 前10个实体
        }
        
        return {
            "success": True,
            "data": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")


@router.get("/knowledge-graph/entity/{entity_id}")
async def get_entity_info(entity_id: str, relation: Optional[str] = None, limit: int = 10):
    """查询实体相关信息"""
    try:
        _ensure_knowledge_graph_built()
        kg = knowledge_graph_service.kg
        related = kg.query_entity(entity_id, relation, limit)
        
        entity_info = kg.entities.get(entity_id, {})
        
        return {
            "success": True,
            "data": {
                "entity": entity_info,
                "related_entities": related
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询实体失败: {str(e)}")


@router.get("/knowledge-graph/graph-data")
async def get_graph_data(role_id: Optional[str] = None):
    """
    获取完整的知识图谱数据（用于可视化）
    
    参数：
    - role_id: 角色ID，如果提供则只返回该角色的知识图谱
    """
    try:
        _ensure_knowledge_graph_built(role_id)
        kg = knowledge_graph_service.kg
        
        # 如果知识图谱为空，返回空数据而不是错误
        if not kg.entities and not kg.triples:
            return {
                "success": True,
                "data": {
                    "nodes": [],
                    "edges": [],
                    "stats": {
                        "entities_count": 0,
                        "triples_count": 0,
                        "relations_count": 0
                    }
                }
            }
        
        # 构建节点数据
        nodes = []
        for entity_id, entity_data in kg.entities.items():
            # 如果指定了role_id，只返回匹配的实体
            entity_role_id = entity_data.get("properties", {}).get("role_id")
            if role_id and entity_role_id != role_id:
                continue
                
            nodes.append({
                "id": entity_id,
                "label": entity_data.get("properties", {}).get("name") or entity_id,
                "type": entity_data.get("type", "unknown"),
                "properties": entity_data.get("properties", {})
            })
        
        # 构建边数据
        edges = []
        for triple in kg.triples:
            subject, relation, obj = triple
            # 如果指定了role_id，只返回匹配的边（两个实体都属于该角色）
            if role_id:
                subject_entity = kg.entities.get(subject, {})
                obj_entity = kg.entities.get(obj, {})
                subject_role_id = subject_entity.get("properties", {}).get("role_id")
                obj_role_id = obj_entity.get("properties", {}).get("role_id")
                if subject_role_id != role_id or obj_role_id != role_id:
                    continue
                    
            edges.append({
                "from": subject,
                "to": obj,
                "label": relation,
                "arrows": "to"
            })
        
        return {
            "success": True,
            "data": {
                "nodes": nodes,
                "edges": edges,
                "stats": {
                    "entities_count": len(nodes),
                    "triples_count": len(edges),
                    "relations_count": len(set(e["label"] for e in edges)) if edges else 0
                }
            }
        }
    except Exception as e:
        logger.error(f"获取图谱数据失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取图谱数据失败: {str(e)}")





