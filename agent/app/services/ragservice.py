"""
RAG服务
实现文档检索和知识库管理
"""
import logging
import os
import json
import hashlib
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class RAGService:
    """RAG服务类"""
    
    def __init__(self, data_dir: str = "data/rag", use_vector_db: bool = False):
        """
        初始化RAG服务
        
        Args:
            data_dir: 数据存储目录
            use_vector_db: 是否使用向量数据库（需要安装相应库）
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 文档存储（内存）
        self.documents: Dict[str, Dict] = {}
        
        # 文档索引（简化版：基于关键词）
        self.index: Dict[str, List[str]] = {}
        
        # 向量数据库支持
        self.use_vector_db = use_vector_db
        self.vector_db = None
        if use_vector_db:
            self._init_vector_db()
        
        # 加载已保存的文档
        self._load_documents()
    
    def _init_vector_db(self):
        """初始化向量数据库"""
        try:
            # 尝试使用ChromaDB（轻量级向量数据库）
            import chromadb
            from chromadb.config import Settings
            
            chroma_dir = self.data_dir / "chroma_db"
            chroma_dir.mkdir(exist_ok=True)
            
            # 兼容不同版本的ChromaDB
            try:
                # 尝试新版本API（0.4.x+）
                self.vector_client = chromadb.PersistentClient(
                    path=str(chroma_dir),
                    settings=Settings(
                        anonymized_telemetry=False,
                        allow_reset=True
                    )
                )
            except TypeError:
                # 回退到旧版本API
                self.vector_client = chromadb.PersistentClient(
                    path=str(chroma_dir)
                )
            
            # 创建或获取集合（处理版本兼容性）
            try:
                self.vector_collection = self.vector_client.get_or_create_collection(
                    name="rag_documents",
                    metadata={"hnsw:space": "cosine"}
                )
            except Exception as e:
                # 如果失败，尝试删除并重新创建集合
                logger.warning(f"获取集合失败，尝试重新创建: {e}")
                try:
                    self.vector_client.delete_collection("rag_documents")
                except:
                    pass
                self.vector_collection = self.vector_client.create_collection(
                    name="rag_documents",
                    metadata={"hnsw:space": "cosine"}
                )
            
            self.use_vector_db = True
            logger.info("向量数据库初始化成功（ChromaDB）")
        except ImportError:
            logger.warning("ChromaDB未安装，使用关键词索引。安装: pip install chromadb")
            self.use_vector_db = False
        except Exception as e:
            logger.warning(f"向量数据库初始化失败: {e}，使用关键词索引")
            self.use_vector_db = False
            # 确保不使用向量数据库
            self.vector_client = None
            self.vector_collection = None

    def _load_documents(self):
        """从文件加载文档"""
        doc_file = self.data_dir / "documents.json"
        if doc_file.exists():
            try:
                with open(doc_file, 'r', encoding='utf-8') as f:
                    self.documents = json.load(f)
                # 只在第一次加载时记录日志
                if not hasattr(RAGService, '_load_logged'):
                    logger.info(f"✅ 加载了 {len(self.documents)} 个文档")
                    RAGService._load_logged = True
            except Exception as e:
                logger.error(f"加载文档失败: {e}")
    
    def _save_documents(self):
        """保存文档到文件"""
        doc_file = self.data_dir / "documents.json"
        try:
            with open(doc_file, 'w', encoding='utf-8') as f:
                json.dump(self.documents, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存文档失败: {e}")
    
    def _extract_text(self, file_data: bytes, filename: str) -> str:
        """
        从文件数据中提取文本
        
        优先级：高级文档处理器 > 增强文档处理器 > 基础实现
        已集成easydoc、mineru、pdfplumber等文档处理工具支持
        """
        try:
            # 优先使用高级文档处理器（集成easydoc、mineru等）
            try:
                from app.services.documentprocessoradvanced import document_processor_advanced
                from app.config import settings
                
                use_enhanced = getattr(settings, 'DOCUMENT_PROCESSOR_USE_ENHANCED', True)
                method = getattr(settings, 'DOCUMENT_PROCESSOR_METHOD', 'auto')
                
                result = document_processor_advanced.extract_text(
                    file_data=file_data,
                    filename=filename,
                    use_enhanced=use_enhanced,
                    method=None if method == 'auto' else method
                )
                
                if result.get("success"):
                    logger.debug(f"使用 {result.get('method')} 提取文本: {filename}")
                    return result.get("text", "")
                else:
                    logger.warning(f"高级文档处理器提取失败: {result.get('error')}")
            except ImportError:
                logger.debug("高级文档处理器不可用，尝试增强文档处理器")
            
            # 回退到增强文档处理器
            try:
                from app.services.documentprocessorenhanced import enhanced_document_processor
                
                result = enhanced_document_processor.extract_text(
                    file_data=file_data,
                    filename=filename,
                    use_enhanced=True
                )
                
                if result.get("success"):
                    return result.get("text", "")
                else:
                    logger.warning(f"增强文档处理器提取失败: {result.get('error')}")
            except ImportError:
                logger.debug("增强文档处理器不可用，使用基础实现")
            
            # 最终回退到基础实现
            try:
                if filename.endswith('.txt') or filename.endswith('.md'):
                    return file_data.decode('utf-8')
                elif filename.endswith('.json'):
                    data = json.loads(file_data.decode('utf-8'))
                    return json.dumps(data, ensure_ascii=False)
                else:
                    logger.warning(f"不支持的文件格式: {filename}")
                    return f"[文档内容: {filename}]"
            except Exception as e:
                logger.error(f"提取文本失败: {e}")
                return ""
        except Exception as e:
            logger.error(f"文档处理异常: {e}", exc_info=True)
            return ""
    
    def _build_index(self, doc_id: str, text: str):
        """构建文档索引"""
        # 关键词索引
        words = text.lower().split()
        keywords = [w for w in words if len(w) > 2][:100]  # 限制关键词数量
        self.index[doc_id] = keywords
        
        # 向量索引（如果启用）
        if self.use_vector_db and self.vector_collection:
            try:
                # 生成文本向量（使用embedding服务）
                # 注意：这里需要异步调用，但_build_index是同步方法
                # 在实际使用中，应该在异步上下文中调用
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # 如果事件循环正在运行，创建任务
                        embedding = asyncio.create_task(self._generate_embedding(text))
                        embedding = loop.run_until_complete(embedding)
                    else:
                        embedding = loop.run_until_complete(self._generate_embedding(text))
                except RuntimeError:
                    # 如果没有事件循环，创建新的
                    embedding = asyncio.run(self._generate_embedding(text))
                
                # 添加到向量数据库
                self.vector_collection.add(
                    ids=[doc_id],
                    embeddings=[embedding],
                    documents=[text[:1000]],  # 限制长度
                    metadatas=[{"doc_id": doc_id}]
                )
            except Exception as e:
                logger.warning(f"向量索引构建失败: {e}")
    
    async def _generate_embedding(self, text: str) -> List[float]:
        """
        生成文本向量（使用embedding服务）
        
        优先使用通义千问embedding API，如果不可用则降级到TF-IDF
        """
        try:
            # 优先使用embedding服务
            from app.services.embeddingservice import embedding_service
            return await embedding_service.generate_embedding(text)
        except Exception as e:
            logger.warning(f"使用embedding服务失败: {e}，尝试sentence-transformers")
            # 尝试使用sentence-transformers（如果已安装）
            try:
                from sentence_transformers import SentenceTransformer
                model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
                embedding = model.encode(text).tolist()
                return embedding
            except ImportError:
                # 回退到简单的词频向量
                logger.warning("sentence-transformers未安装，使用简化向量。安装: pip install sentence-transformers")
                words = text.lower().split()
                word_freq = {}
                for word in words:
                    word_freq[word] = word_freq.get(word, 0) + 1
                
                # 创建固定维度的向量（128维）
                embedding = [0.0] * 128
                for i, (word, freq) in enumerate(list(word_freq.items())[:128]):
                    embedding[i] = freq / len(words) if words else 0.0
                
                return embedding
    
    def _rebuild_index(self):
        """重建所有文档索引"""
        self.index = {}
        for doc_id, doc_data in self.documents.items():
            text = doc_data.get("text", "")
            self._build_index(doc_id, text)
    
    def upload_document(
        self,
        file_data: bytes,
        filename: str,
        metadata: Optional[Dict] = None,
        role_id: Optional[str] = None
    ) -> str:
        """
        上传文档到知识库
        
        Args:
            file_data: 文件数据
            filename: 文件名
            metadata: 元数据
            role_id: 角色ID（用于分类知识库）
        
        Returns:
            文档ID
        """
        try:
            # 生成文档ID（包含role_id以确保不同角色的文档ID不同）
            doc_id_base = f"{role_id}_{filename}" if role_id else filename
            doc_id = hashlib.md5(f"{doc_id_base}_{file_data}".encode()).hexdigest()
            
            # 提取文本
            text = self._extract_text(file_data, filename)
            
            # 保存文档
            doc_metadata = metadata or {}
            if role_id:
                doc_metadata["role_id"] = role_id
            
            self.documents[doc_id] = {
                "doc_id": doc_id,
                "filename": filename,
                "text": text,
                "metadata": doc_metadata,
                "role_id": role_id,  # 添加角色ID字段
                "upload_time": datetime.now().isoformat(),
                "size": len(file_data)
            }
            
            # 构建索引
            self._build_index(doc_id, text)
            
            # 保存到文件
            self._save_documents()
            
            logger.info(f"文档上传成功: {filename} (ID: {doc_id})")
            return doc_id
            
        except Exception as e:
            logger.error(f"文档上传失败: {e}", exc_info=True)
            raise
    
    def search(
        self,
        query: str,
        top_k: int = 5,
        context_id: Optional[str] = None,
        use_vector_search: bool = True,
        role_id: Optional[str] = None
    ) -> List[Dict]:
        """
        搜索相关文档
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            context_id: 上下文ID（可选）
            use_vector_search: 是否使用向量搜索（如果可用）
            role_id: 角色ID（用于过滤知识库）
        
        Returns:
            搜索结果列表
        """
        try:
            # 优先使用向量搜索
            if use_vector_search and self.use_vector_db and self.vector_collection:
                results = self._vector_search(query, top_k, role_id)
            else:
                results = self._keyword_search(query, top_k, role_id)
            
            # 如果指定了role_id，过滤结果
            if role_id:
                results = [r for r in results if r.get("role_id") == role_id or r.get("metadata", {}).get("role_id") == role_id]
            
            return results[:top_k]
        except Exception as e:
            logger.error(f"搜索失败: {e}", exc_info=True)
            # 回退到关键词搜索
            return self._keyword_search(query, top_k, role_id)
    
    def _vector_search(self, query: str, top_k: int, role_id: Optional[str] = None) -> List[Dict]:
        """向量搜索"""
        try:
            # 生成查询向量
            # 异步生成查询向量
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    query_embedding = asyncio.create_task(self._generate_embedding(query))
                    query_embedding = loop.run_until_complete(query_embedding)
                else:
                    query_embedding = loop.run_until_complete(self._generate_embedding(query))
            except RuntimeError:
                query_embedding = asyncio.run(self._generate_embedding(query))
            
            # 在向量数据库中搜索
            results = self.vector_collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k
            )
            
            # 转换结果格式
            search_results = []
            if results['ids'] and len(results['ids'][0]) > 0:
                for i, doc_id in enumerate(results['ids'][0]):
                    doc_data = self.documents.get(doc_id, {})
                    # 如果指定了role_id，只返回匹配的文档
                    if role_id and doc_data.get("role_id") != role_id and doc_data.get("metadata", {}).get("role_id") != role_id:
                        continue
                    search_results.append({
                        "doc_id": doc_id,
                        "filename": doc_data.get("filename", ""),
                        "score": 1.0 - results['distances'][0][i] if 'distances' in results else 0.5,  # 距离转分数
                        "content": doc_data.get("text", "")[:500],
                        "metadata": doc_data.get("metadata", {}),
                        "role_id": doc_data.get("role_id"),
                        "method": "vector_search"
                    })
            
            return search_results
        except Exception as e:
            logger.warning(f"向量搜索失败: {e}，回退到关键词搜索")
            return self._keyword_search(query, top_k, role_id)
    
    def _keyword_search(self, query: str, top_k: int, role_id: Optional[str] = None) -> List[Dict]:
        """关键词搜索"""
        query_words = query.lower().split()
        results = []
        
        # 关键词匹配
        for doc_id, doc_data in self.documents.items():
            # 如果指定了role_id，只搜索匹配的文档
            if role_id and doc_data.get("role_id") != role_id and doc_data.get("metadata", {}).get("role_id") != role_id:
                continue
                
            text = doc_data.get("text", "").lower()
            score = 0
            
            # 计算匹配分数
            for word in query_words:
                if word in text:
                    score += text.count(word)
            
            if score > 0:
                results.append({
                    "doc_id": doc_id,
                    "filename": doc_data.get("filename", ""),
                    "score": score,
                    "content": doc_data.get("text", "")[:500],
                    "metadata": doc_data.get("metadata", {}),
                    "role_id": doc_data.get("role_id"),
                    "method": "keyword_search"
                })
        
        # 按分数排序
        results.sort(key=lambda x: x["score"], reverse=True)
        
        return results[:top_k]
    
    def build_context(self, query: str, search_results: List[Dict]) -> str:
        """
        构建增强上下文
        
        Args:
            query: 查询文本
            search_results: 搜索结果
        
        Returns:
            增强后的上下文
        """
        if not search_results:
            return ""
        
        context_parts = [f"查询: {query}\n\n相关文档内容:\n"]
        
        for i, result in enumerate(search_results, 1):
            context_parts.append(
                f"[文档{i}] {result.get('filename', '未知')}\n"
                f"{result.get('content', '')}\n"
            )
        
        return "\n".join(context_parts)
    
    def enhanced_search(
        self,
        query: str,
        top_k: int = 5,
        use_knowledge_graph: bool = False,
        role_id: Optional[str] = None
    ) -> Dict:
        """
        增强检索（可选知识图谱）
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            use_knowledge_graph: 是否使用知识图谱增强
            role_id: 角色ID（用于过滤知识库）
        
        Returns:
            检索结果（包含向量检索和知识图谱结果）
        """
        try:
            # 向量检索
            vector_results = self.search(query, top_k, role_id=role_id)
            
            # 如果启用知识图谱
            if use_knowledge_graph:
                try:
                    from app.services.knowledgegraphservice import knowledge_graph_service
                    
                    # 混合检索
                    hybrid_result = knowledge_graph_service.hybrid_retrieval(
                        question=query,
                        vector_db_results=vector_results,
                        top_k=top_k
                    )
                    
                    return {
                        "vector_results": vector_results,
                        "kg_results": hybrid_result.get("kg_results", []),
                        "fused_results": hybrid_result.get("fused_results", []),
                        "entities": hybrid_result.get("entities", []),
                        "use_kg": True
                    }
                except ImportError:
                    logger.warning("知识图谱服务未加载，使用标准检索")
                    return {
                        "vector_results": vector_results,
                        "use_kg": False
                    }
            else:
                return {
                    "vector_results": vector_results,
                    "use_kg": False
                }
        except Exception as e:
            logger.error(f"增强检索失败: {e}", exc_info=True)
            return {
                "vector_results": [],
                "use_kg": False,
                "error": str(e)
            }