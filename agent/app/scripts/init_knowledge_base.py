#!/usr/bin/env python3
"""
初始化知识库脚本
将示例知识文档导入到知识库，并按角色分类
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.services.ragservice import RAGService

# 角色ID映射（根据实际角色名称或ID）
ROLE_MAPPING = {
    "律师": "lawyer",
    "教师": "teacher", 
    "程序员": "programmer",
    "作家": "writer"
}

def init_knowledge_base():
    """初始化知识库"""
    print("开始初始化知识库...")
    
    # 初始化RAG服务
    rag_service = RAGService()
    
    # 知识库文件目录
    knowledge_base_dir = Path(__file__).parent.parent / "data" / "rag" / "knowledge_base"
    
    if not knowledge_base_dir.exists():
        print(f"知识库目录不存在: {knowledge_base_dir}")
        return
    
    # 遍历知识库文件
    imported_count = 0
    for file_path in knowledge_base_dir.glob("*.md"):
        # 从文件名提取角色名称（格式：角色名-知识库.md）
        role_name = file_path.stem.split("-")[0]
        role_id = ROLE_MAPPING.get(role_name)
        
        if not role_id:
            print(f"跳过未知角色文件: {file_path.name}")
            continue
        
        try:
            # 清理同名同角色的旧种子文档，避免重复导入
            duplicate_ids = [
                doc_id
                for doc_id, doc_data in rag_service.documents.items()
                if doc_data.get("filename") == file_path.name
                and doc_data.get("role_id") == role_id
                and doc_data.get("metadata", {}).get("source") == "knowledge_base"
            ]
            for duplicate_id in duplicate_ids:
                rag_service.documents.pop(duplicate_id, None)
            if duplicate_ids:
                rag_service._save_documents()

            # 读取文件内容
            with open(file_path, 'r', encoding='utf-8') as f:
                file_data = f.read().encode('utf-8')
            
            # 上传到知识库
            doc_id = rag_service.upload_document(
                file_data=file_data,
                filename=file_path.name,
                metadata={
                    "source": "knowledge_base",
                    "role_name": role_name,
                    "auto_imported": True
                },
                role_id=role_id
            )
            
            print(f"已导入: {file_path.name} -> 角色: {role_name} (ID: {role_id})")
            imported_count += 1
            
        except Exception as e:
            print(f"导入失败 {file_path.name}: {e}")
    
    print(f"\n知识库初始化完成！共导入 {imported_count} 个文档")
    print(f"文档已按角色分类存储")
    print(f"   - 律师 (lawyer)")
    print(f"   - 教师 (teacher)")
    print(f"   - 程序员 (programmer)")
    print(f"   - 作家 (writer)")

if __name__ == "__main__":
    init_knowledge_base()

