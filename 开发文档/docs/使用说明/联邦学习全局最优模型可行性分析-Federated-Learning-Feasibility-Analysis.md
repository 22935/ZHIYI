# 联邦学习全局最优模型系统 - 可行性分析与实现方案

## 📋 目录

1. [创新点概述](#创新点概述)
2. [可行性分析](#可行性分析)
3. [创新价值评估](#创新价值评估)
4. [技术架构设计](#技术架构设计)
5. [详细实现方案](#详细实现方案)
6. [安全与隐私保护](#安全与隐私保护)
7. [实施路线图](#实施路线图)

---

## 1. 创新点概述

### 1.1 核心理念

**数据不动模型动，参数可用不可见**

这是一个基于联邦学习的全局最优模型系统,实现以下核心流程:

1. **基础模型训练**: 使用公开大数据训练一个基础模型
2. **模型分发**: 将基础模型发送到各个客户端(如机构A、B、C)
3. **本地私有训练**: 
   - 客户端使用私有数据进行增量训练
   - 构建本地私有RAG知识库
   - 针对本地场景优化模型
4. **参数加密上传**: 
   - 只上传模型参数更新(不是原始数据)
   - 参数经过加密和差分隐私处理
5. **云端聚合**: 
   - 安全聚合多个客户端的参数更新
   - 生成全局优化模型
6. **全局共享**: 
   - 所有客户端都可以使用全局优化模型
   - 享受其他客户端训练成果，但看不到原始数据

### 1.2 关键特点

- ✅ **数据隐私保护**: 原始数据永远不离开本地
- ✅ **知识共享**: 模型改进在全局共享
- ✅ **持续优化**: 模型随着更多客户端参与持续优化
- ✅ **差异化优势**: 每个客户端既有私有知识库，又能享受全局智能
- ✅ **安全合规**: 符合数据安全法规要求

---

## 2. 可行性分析

### 2.1 技术可行性 ⭐⭐⭐⭐⭐ (5/5)

#### 2.1.1 已有技术基础

您的项目**已经具备**联邦学习的核心组件:

| 组件 | 状态 | 文件位置 |
|------|------|----------|
| 联邦学习服务 | ✅ 已实现 | `agent/app/services/federatedlearning.py` |
| 参数聚合算法 | ✅ 已实现 | FederatedLearningService.aggregate_parameters |
| 差分隐私保护 | ✅ 已实现 | EncryptionService.add_differential_privacy |
| 参数加密 | ✅ 已实现 | EncryptionService.encrypt_parameters |
| RAG知识库 | ✅ 已实现 | RAGService, EnhancedRAGService |
| 模型选择器 | ✅ 已实现 | ModelSelector, FederatedModelOptimizer |
| 知识图谱 | ✅ 已实现 | KnowledgeGraphService |

**结论**: 技术基础非常扎实，**可以在现有代码上直接扩展**，无需从零开始。

#### 2.1.2 缺失部分

需要新增的核心功能:

1. **客户端训练管理器** - 管理本地训练流程
2. **全局模型版本管理** - 追踪模型版本和演进
3. **RAG联邦优化** - 将联邦学习应用到RAG知识库
4. **客户端-云端同步机制** - 管理参数上传下载
5. **可视化监控面板** - 展示联邦学习网络状态

**评估**: 这些都是常规功能，实现难度不大。

### 2.2 商业可行性 ⭐⭐⭐⭐⭐ (5/5)

#### 2.2.1 市场需求

| 应用场景 | 痛点 | 本方案优势 |
|---------|------|-----------|
| **医疗行业** | 医疗数据敏感，无法共享 | 多医院协作训练，数据不出院 |
| **金融行业** | 客户隐私保护要求高 | 多银行共建风控模型，数据保密 |
| **教育行业** | 学生数据受保护 | 多学校共享教学智能，保护隐私 |
| **政企客户** | 内部数据绝对保密 | 享受外部智能，内部数据不外泄 |
| **跨国企业** | 各国数据监管严格 | 全球模型优化，符合各国法规 |

**市场规模**: 联邦学习市场预计2025年达到**30亿美元**，年增长率**40%+**

#### 2.2.2 竞争优势

相比竞品:

- ✅ **集成RAG**: 不仅模型参数，还有知识库优化
- ✅ **银河麒麟适配**: 符合国产化要求
- ✅ **数字人应用**: 将联邦学习应用到数字人生成
- ✅ **开箱即用**: 完整系统，不只是算法库

### 2.3 法律合规性 ⭐⭐⭐⭐⭐ (5/5)

#### 2.3.1 符合法规

- ✅ **《数据安全法》**: 数据不出境，不离开本地
- ✅ **《个人信息保护法》**: 原始数据不共享
- ✅ **GDPR**: 符合欧盟数据保护要求
- ✅ **等保2.0**: 支持分级保护

#### 2.3.2 隐私保护措施

1. **差分隐私**: ε-差分隐私保证(已实现)
2. **同态加密**: 参数加密传输(已实现)
3. **安全聚合**: MPC多方安全计算(可扩展)
4. **访问控制**: 基于角色的权限管理

### 2.4 实施可行性 ⭐⭐⭐⭐ (4/5)

#### 2.4.1 优势

- ✅ 技术栈成熟(Python + FastAPI + Vue)
- ✅ 已有完整RAG系统
- ✅ 已有联邦学习基础框架
- ✅ 已有加密和隐私保护组件

#### 2.4.2 挑战

- ⚠️ 需要客户端部署能力
- ⚠️ 网络通信质量要求
- ⚠️ 多客户端协调复杂度

**缓解方案**: 
- 提供Docker一键部署
- 支持断点续传和离线训练
- 自动化协调调度

---

## 3. 创新价值评估

### 3.1 技术创新价值 ⭐⭐⭐⭐⭐

#### 3.1.1 首创性

| 创新点 | 创新程度 | 说明 |
|-------|---------|------|
| RAG联邦优化 | 🌟🌟🌟🌟🌟 | **业界首创**将联邦学习应用到RAG知识库优化 |
| 数字人联邦训练 | 🌟🌟🌟🌟🌟 | 联邦学习优化数字人生成模型 |
| 知识图谱联邦构建 | 🌟🌟🌟🌟 | 多方协作构建知识图谱 |
| 银河麒麟深度集成 | 🌟🌟🌟🌟 | 国产化环境下的联邦学习 |

#### 3.1.2 核心技术突破

1. **RAG联邦优化**
   ```
   传统RAG: 每个机构独立构建知识库 → 知识孤岛
   
   本方案: 
   - 本地私有知识库保密
   - 共享检索优化策略
   - 全局语义理解提升
   - 跨机构知识增强
   ```

2. **混合智能模式**
   ```
   基础模型(公开数据) 
        ↓
   + 本地增量训练(私有数据)
        ↓
   + 联邦学习优化(全局智能)
        ↓
   = 个性化+全局最优
   ```

### 3.2 商业价值 ⭐⭐⭐⭐⭐

#### 3.2.1 收益模式

| 收益来源 | 预期收益 | 说明 |
|---------|---------|------|
| **License授权** | 高 | 按客户端数量收费 |
| **SaaS订阅** | 高 | 云端聚合服务订阅 |
| **技术服务** | 中 | 部署、定制、咨询 |
| **数据见解** | 中 | 聚合分析报告(匿名化) |

#### 3.2.2 竞争壁垒

- 🔒 **技术壁垒**: RAG+联邦学习深度融合
- 🔒 **先发优势**: 首个完整实现的商用系统
- 🔒 **生态壁垒**: 银河麒麟国产化生态
- 🔒 **数据网络效应**: 客户越多，模型越好

### 3.3 社会价值 ⭐⭐⭐⭐⭐

#### 3.3.1 隐私保护

- 解决数据孤岛问题
- 保护个人隐私
- 符合监管要求

#### 3.3.2 知识共享

- 促进跨组织协作
- 提升整体AI能力
- 降低AI使用门槛

### 3.4 学术价值 ⭐⭐⭐⭐

#### 3.4.1 论文发表潜力

- **顶会**: NeurIPS、ICML、ICLR (联邦学习+RAG融合)
- **期刊**: TPAMI、TNNLS (知识图谱联邦构建)
- **应用**: AAAI、KDD (实际应用案例)

#### 3.4.2 专利布局

建议申请专利:
1. 基于联邦学习的RAG知识库优化方法
2. 跨机构知识图谱协同构建系统
3. 隐私保护的数字人模型训练方法

---

## 4. 技术架构设计

### 4.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                      云端聚合服务器                           │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  全局模型管理                                         │    │
│  │  - 版本管理    - 参数聚合    - 质量评估             │    │
│  └─────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  安全聚合引擎                                         │    │
│  │  - 参数解密    - 差分隐私    - 安全聚合             │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                            ↕  ↕  ↕
                  (加密参数上传/模型下载)
                            ↕  ↕  ↕
┌──────────┐      ┌──────────┐      ┌──────────┐
│ 客户端A   │      │ 客户端B   │      │ 客户端C   │
│┌────────┐│      │┌────────┐│      │┌────────┐│
││基础模型││      ││基础模型││      ││基础模型││
││   +    ││      ││   +    ││      ││   +    ││
││本地训练││      ││本地训练││      ││本地训练││
││   +    ││      ││   +    ││      ││   +    ││
││私有RAG ││      ││私有RAG ││      ││私有RAG ││
│└────────┘│      │└────────┘│      │└────────┘│
│          │      │          │      │          │
│ 私有数据 │      │ 私有数据 │      │ 私有数据 │
│ (不上传) │      │ (不上传) │      │ (不上传) │
└──────────┘      └──────────┘      └──────────┘
```

### 4.2 核心组件

#### 4.2.1 云端组件

```python
# 全局模型管理器
GlobalModelManager:
    - register_client()        # 注册客户端
    - distribute_model()       # 分发基础模型
    - collect_updates()        # 收集参数更新
    - aggregate_parameters()   # 聚合参数
    - version_control()        # 版本管理
    - quality_evaluation()     # 质量评估

# 安全聚合引擎
SecureAggregationEngine:
    - decrypt_parameters()     # 参数解密
    - verify_privacy()         # 隐私验证
    - aggregate_secure()       # 安全聚合
    - detect_anomaly()         # 异常检测
```

#### 4.2.2 客户端组件

```python
# 本地训练管理器
LocalTrainingManager:
    - download_global_model()  # 下载全局模型
    - train_on_local_data()    # 本地训练
    - build_local_rag()        # 构建本地RAG
    - extract_parameters()     # 提取参数更新
    - encrypt_upload()         # 加密上传

# 私有RAG管理器
PrivateRAGManager:
    - build_knowledge_base()   # 构建知识库
    - optimize_retrieval()     # 优化检索
    - extract_insights()       # 提取知识见解
    - protect_privacy()        # 隐私保护
```

### 4.3 数据流程

#### 4.3.1 初始化阶段

```
1. 云端训练基础模型(使用公开数据)
   ↓
2. 客户端注册并下载基础模型
   ↓
3. 客户端验证模型完整性
```

#### 4.3.2 本地训练阶段

```
1. 加载基础模型到本地
   ↓
2. 使用本地私有数据增量训练
   ↓
3. 构建本地私有RAG知识库
   ↓
4. 提取模型参数更新Δθ
   ↓
5. 添加差分隐私噪声: Δθ' = Δθ + Noise(ε, δ)
   ↓
6. 加密参数: E(Δθ')
```

#### 4.3.3 参数聚合阶段

```
1. 收集多个客户端的加密参数: {E(Δθ₁'), E(Δθ₂'), ..., E(Δθₙ')}
   ↓
2. 在安全环境中解密: {Δθ₁', Δθ₂', ..., Δθₙ'}
   ↓
3. 加权聚合: Δθ_global = Σ wᵢ * Δθᵢ'
   ↓
4. 更新全局模型: θ_global = θ_global + Δθ_global
   ↓
5. 质量评估和版本控制
   ↓
6. 分发新版本全局模型
```

### 4.4 核心算法

#### 4.4.1 联邦平均算法(FedAvg)

```python
def federated_averaging(
    global_model: Dict,
    client_updates: List[Dict],
    client_weights: List[float]
) -> Dict:
    """
    联邦平均算法
    
    Args:
        global_model: 全局模型参数
        client_updates: 客户端参数更新列表
        client_weights: 客户端权重(通常与数据量成正比)
    
    Returns:
        更新后的全局模型
    """
    # 1. 归一化权重
    total_weight = sum(client_weights)
    weights = [w / total_weight for w in client_weights]
    
    # 2. 加权平均
    aggregated_update = {}
    for key in client_updates[0].keys():
        aggregated_update[key] = sum(
            weights[i] * np.array(client_updates[i][key])
            for i in range(len(client_updates))
        )
    
    # 3. 更新全局模型
    updated_model = {}
    for key in global_model.keys():
        updated_model[key] = (
            np.array(global_model[key]) + 
            aggregated_update.get(key, 0)
        )
    
    return updated_model
```

#### 4.4.2 差分隐私保护

```python
def add_differential_privacy(
    parameters: Dict,
    epsilon: float = 1.0,
    delta: float = 1e-5,
    sensitivity: float = 1.0
) -> Dict:
    """
    添加差分隐私噪声
    
    Args:
        parameters: 原始参数
        epsilon: 隐私预算(越小越私密)
        delta: 失败概率
        sensitivity: 敏感度
    
    Returns:
        添加噪声后的参数
    """
    # 高斯噪声标准差
    sigma = sensitivity * sqrt(2 * log(1.25 / delta)) / epsilon
    
    noisy_parameters = {}
    for key, value in parameters.items():
        # 添加高斯噪声
        noise = np.random.normal(0, sigma, size=np.array(value).shape)
        noisy_parameters[key] = np.array(value) + noise
    
    return noisy_parameters
```

#### 4.4.3 RAG联邦优化

```python
class FederatedRAGOptimizer:
    """RAG联邦优化器"""
    
    def optimize_retrieval_strategy(
        self,
        local_rag_stats: List[Dict],  # 各客户端RAG统计
        global_queries: List[str]      # 全局查询样本
    ) -> Dict:
        """
        优化全局检索策略
        
        流程:
        1. 收集各客户端的检索统计(不含原始文档)
        2. 分析全局检索模式
        3. 优化检索参数(top_k, 相似度阈值等)
        4. 生成优化建议
        """
        # 1. 聚合检索统计
        aggregated_stats = self._aggregate_rag_stats(local_rag_stats)
        
        # 2. 分析检索模式
        patterns = self._analyze_retrieval_patterns(aggregated_stats)
        
        # 3. 优化参数
        optimized_params = {
            'top_k': self._optimize_top_k(patterns),
            'similarity_threshold': self._optimize_threshold(patterns),
            'reranking_strategy': self._select_reranking(patterns)
        }
        
        # 4. 生成全局语义增强模型
        semantic_model = self._train_semantic_model(
            global_queries,
            aggregated_stats
        )
        
        return {
            'params': optimized_params,
            'semantic_model': semantic_model,
            'insights': patterns
        }
```

---

## 5. 详细实现方案

### 5.1 Phase 1: 云端基础设施 (2周)

#### 5.1.1 全局模型管理服务

**文件**: `agent/app/services/globalmodelmanager.py`

```python
"""
全局模型管理服务
管理联邦学习的全局模型,包括版本控制、分发、聚合
"""
import logging
import hashlib
import json
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class ModelVersion:
    """模型版本"""
    def __init__(self, version_id: str, model_params: Dict, metadata: Dict):
        self.version_id = version_id
        self.model_params = model_params
        self.metadata = metadata
        self.created_at = datetime.now()
        self.clients_count = 0
        self.performance_metrics = {}


class GlobalModelManager:
    """全局模型管理器"""
    
    def __init__(self, model_storage_dir: str = "data/global_models"):
        self.storage_dir = Path(model_storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # 当前全局模型
        self.current_model: Optional[ModelVersion] = None
        
        # 模型版本历史
        self.version_history: List[ModelVersion] = []
        
        # 已注册客户端
        self.registered_clients: Dict[str, Dict] = {}
        
        # 待聚合的参数更新
        self.pending_updates: List[Dict] = []
        
        logger.info("全局模型管理器已初始化")
    
    def initialize_base_model(
        self,
        model_type: str,
        model_params: Dict,
        training_data_info: Dict
    ) -> str:
        """
        初始化基础模型
        
        Args:
            model_type: 模型类型(text_generation/rag/digital_human)
            model_params: 模型参数
            training_data_info: 训练数据信息
        
        Returns:
            模型版本ID
        """
        version_id = self._generate_version_id(model_params)
        
        metadata = {
            'model_type': model_type,
            'training_data': training_data_info,
            'created_at': datetime.now().isoformat(),
            'version': '1.0.0'
        }
        
        self.current_model = ModelVersion(version_id, model_params, metadata)
        self.version_history.append(self.current_model)
        
        # 保存到磁盘
        self._save_model(self.current_model)
        
        logger.info(f"基础模型已初始化: {version_id}")
        return version_id
    
    def register_client(
        self,
        client_id: str,
        client_info: Dict
    ) -> Dict:
        """
        注册客户端
        
        Args:
            client_id: 客户端ID
            client_info: 客户端信息(名称、机构、数据规模等)
        
        Returns:
            注册信息(包含当前全局模型版本)
        """
        if client_id in self.registered_clients:
            logger.warning(f"客户端已注册: {client_id}")
        
        self.registered_clients[client_id] = {
            'client_id': client_id,
            'info': client_info,
            'registered_at': datetime.now().isoformat(),
            'current_model_version': self.current_model.version_id if self.current_model else None,
            'upload_count': 0,
            'last_upload': None
        }
        
        logger.info(f"客户端已注册: {client_id}")
        
        return {
            'success': True,
            'client_id': client_id,
            'current_model_version': self.current_model.version_id if self.current_model else None,
            'model_params': self.current_model.model_params if self.current_model else None
        }
    
    def distribute_model(
        self,
        client_id: str
    ) -> Dict:
        """
        分发全局模型到客户端
        
        Args:
            client_id: 客户端ID
        
        Returns:
            模型信息
        """
        if client_id not in self.registered_clients:
            raise ValueError(f"客户端未注册: {client_id}")
        
        if not self.current_model:
            raise ValueError("全局模型未初始化")
        
        logger.info(f"分发模型 {self.current_model.version_id} 到客户端 {client_id}")
        
        return {
            'version_id': self.current_model.version_id,
            'model_params': self.current_model.model_params,
            'metadata': self.current_model.metadata,
            'download_time': datetime.now().isoformat()
        }
    
    def collect_update(
        self,
        client_id: str,
        encrypted_update: Dict,
        update_metadata: Dict
    ) -> Dict:
        """
        收集客户端参数更新
        
        Args:
            client_id: 客户端ID
            encrypted_update: 加密的参数更新
            update_metadata: 更新元数据(训练轮次、数据量等)
        
        Returns:
            收集结果
        """
        if client_id not in self.registered_clients:
            raise ValueError(f"客户端未注册: {client_id}")
        
        # 存储待聚合的更新
        self.pending_updates.append({
            'client_id': client_id,
            'update': encrypted_update,
            'metadata': update_metadata,
            'timestamp': datetime.now().isoformat()
        })
        
        # 更新客户端统计
        self.registered_clients[client_id]['upload_count'] += 1
        self.registered_clients[client_id]['last_upload'] = datetime.now().isoformat()
        
        logger.info(f"收集到客户端 {client_id} 的参数更新")
        
        return {
            'success': True,
            'client_id': client_id,
            'pending_updates_count': len(self.pending_updates),
            'ready_to_aggregate': len(self.pending_updates) >= self._get_aggregation_threshold()
        }
    
    def aggregate_updates(
        self,
        min_clients: int = 3
    ) -> Dict:
        """
        聚合客户端参数更新
        
        Args:
            min_clients: 最小客户端数量
        
        Returns:
            聚合结果
        """
        if len(self.pending_updates) < min_clients:
            raise ValueError(f"参数更新数量不足,需要至少{min_clients}个")
        
        logger.info(f"开始聚合{len(self.pending_updates)}个客户端的参数更新")
        
        # 1. 解密参数(使用加密服务)
        from app.services.encryptionservice import encryption_service
        decrypted_updates = []
        for update_info in self.pending_updates:
            decrypted = encryption_service.decrypt_parameters(
                update_info['update']
            )
            decrypted_updates.append({
                'client_id': update_info['client_id'],
                'params': decrypted,
                'metadata': update_info['metadata']
            })
        
        # 2. 计算权重(基于数据量)
        total_data_size = sum(
            u['metadata'].get('data_size', 1.0) 
            for u in decrypted_updates
        )
        weights = [
            u['metadata'].get('data_size', 1.0) / total_data_size
            for u in decrypted_updates
        ]
        
        # 3. 聚合参数(使用联邦学习服务)
        from app.services.federatedlearning import federated_learning_service
        aggregated_params = federated_learning_service.aggregate_parameters(
            client_parameters=[u['params'] for u in decrypted_updates],
            weights=weights
        )
        
        # 4. 更新全局模型
        new_model_params = {}
        for key in self.current_model.model_params.keys():
            if key in aggregated_params:
                # 加权更新: θ_new = θ_old + α * Δθ
                learning_rate = 0.1
                new_model_params[key] = (
                    self.current_model.model_params[key] + 
                    learning_rate * aggregated_params[key]
                )
            else:
                new_model_params[key] = self.current_model.model_params[key]
        
        # 5. 创建新版本
        new_version_id = self._generate_version_id(new_model_params)
        new_metadata = {
            **self.current_model.metadata,
            'version': self._increment_version(self.current_model.metadata['version']),
            'aggregation_info': {
                'clients_count': len(decrypted_updates),
                'client_ids': [u['client_id'] for u in decrypted_updates],
                'aggregated_at': datetime.now().isoformat()
            }
        }
        
        new_model = ModelVersion(new_version_id, new_model_params, new_metadata)
        new_model.clients_count = len(decrypted_updates)
        
        # 6. 更新当前模型
        self.current_model = new_model
        self.version_history.append(new_model)
        
        # 7. 保存模型
        self._save_model(new_model)
        
        # 8. 清空待聚合更新
        self.pending_updates.clear()
        
        logger.info(f"参数聚合完成,新模型版本: {new_version_id}")
        
        return {
            'success': True,
            'new_version_id': new_version_id,
            'version': new_metadata['version'],
            'clients_participated': len(decrypted_updates),
            'aggregated_at': datetime.now().isoformat()
        }
    
    def get_model_history(self) -> List[Dict]:
        """获取模型版本历史"""
        return [
            {
                'version_id': v.version_id,
                'version': v.metadata.get('version'),
                'created_at': v.created_at.isoformat(),
                'clients_count': v.clients_count,
                'performance': v.performance_metrics
            }
            for v in self.version_history
        ]
    
    def get_client_statistics(self) -> Dict:
        """获取客户端统计信息"""
        return {
            'total_clients': len(self.registered_clients),
            'active_clients': sum(
                1 for c in self.registered_clients.values()
                if c['upload_count'] > 0
            ),
            'clients': list(self.registered_clients.values())
        }
    
    def _generate_version_id(self, model_params: Dict) -> str:
        """生成模型版本ID"""
        params_str = json.dumps(model_params, sort_keys=True)
        return hashlib.sha256(params_str.encode()).hexdigest()[:16]
    
    def _increment_version(self, version: str) -> str:
        """递增版本号"""
        parts = version.split('.')
        parts[-1] = str(int(parts[-1]) + 1)
        return '.'.join(parts)
    
    def _get_aggregation_threshold(self) -> int:
        """获取聚合阈值"""
        # 可配置:当收集到足够多的更新时触发聚合
        return 3
    
    def _save_model(self, model: ModelVersion):
        """保存模型到磁盘"""
        model_file = self.storage_dir / f"{model.version_id}.json"
        with open(model_file, 'w') as f:
            json.dump({
                'version_id': model.version_id,
                'params': model.model_params,
                'metadata': model.metadata,
                'created_at': model.created_at.isoformat()
            }, f, indent=2)
        logger.info(f"模型已保存: {model_file}")


# 全局实例
global_model_manager = GlobalModelManager()
```

#### 5.1.2 API路由

**文件**: `agent/app/api/federatedglobal.py`

```python
"""
联邦学习全局模型API
提供云端模型管理接口
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional
from app.services.globalmodelmanager import global_model_manager

router = APIRouter()


class InitializeModelRequest(BaseModel):
    """初始化模型请求"""
    model_type: str
    model_params: Dict
    training_data_info: Dict


class RegisterClientRequest(BaseModel):
    """注册客户端请求"""
    client_id: str
    client_info: Dict


class UploadUpdateRequest(BaseModel):
    """上传参数更新请求"""
    client_id: str
    encrypted_update: Dict
    update_metadata: Dict


@router.post("/global-model/initialize")
async def initialize_base_model(request: InitializeModelRequest):
    """初始化基础模型"""
    try:
        version_id = global_model_manager.initialize_base_model(
            model_type=request.model_type,
            model_params=request.model_params,
            training_data_info=request.training_data_info
        )
        
        return {
            'success': True,
            'version_id': version_id,
            'message': '基础模型已初始化'
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/global-model/register-client")
async def register_client(request: RegisterClientRequest):
    """注册客户端"""
    try:
        result = global_model_manager.register_client(
            client_id=request.client_id,
            client_info=request.client_info
        )
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/global-model/download/{client_id}")
async def download_model(client_id: str):
    """下载全局模型"""
    try:
        model_info = global_model_manager.distribute_model(client_id)
        
        return {
            'success': True,
            'model': model_info
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/global-model/upload-update")
async def upload_update(request: UploadUpdateRequest):
    """上传参数更新"""
    try:
        result = global_model_manager.collect_update(
            client_id=request.client_id,
            encrypted_update=request.encrypted_update,
            update_metadata=request.update_metadata
        )
        
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/global-model/aggregate")
async def aggregate_updates(min_clients: int = 3):
    """聚合参数更新"""
    try:
        result = global_model_manager.aggregate_updates(min_clients=min_clients)
        
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/global-model/history")
async def get_model_history():
    """获取模型历史"""
    try:
        history = global_model_manager.get_model_history()
        
        return {
            'success': True,
            'history': history
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/global-model/clients")
async def get_client_statistics():
    """获取客户端统计"""
    try:
        stats = global_model_manager.get_client_statistics()
        
        return {
            'success': True,
            'statistics': stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### 5.2 Phase 2: 客户端训练管理器 (2周)

#### 5.2.1 本地训练管理器

**文件**: `agent/app/services/localtrainingmanager.py`

```python
"""
本地训练管理器
管理客户端的本地训练流程
"""
import logging
import json
import requests
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class LocalTrainingManager:
    """本地训练管理器"""
    
    def __init__(
        self,
        client_id: str,
        server_url: str,
        local_data_dir: str = "data/local_training"
    ):
        self.client_id = client_id
        self.server_url = server_url
        self.local_data_dir = Path(local_data_dir)
        self.local_data_dir.mkdir(parents=True, exist_ok=True)
        
        # 当前模型
        self.current_model: Optional[Dict] = None
        self.current_version: Optional[str] = None
        
        # 本地私有数据
        self.private_data: List[Dict] = []
        
        # 本地RAG知识库
        self.local_rag = None
        
        logger.info(f"本地训练管理器已初始化,客户端ID: {client_id}")
    
    def register_to_server(self, client_info: Dict) -> Dict:
        """
        注册到服务器
        
        Args:
            client_info: 客户端信息
        
        Returns:
            注册结果
        """
        try:
            response = requests.post(
                f"{self.server_url}/api/global-model/register-client",
                json={
                    'client_id': self.client_id,
                    'client_info': client_info
                }
            )
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"注册成功: {self.client_id}")
            
            # 下载初始模型
            if result.get('current_model_version'):
                self._download_model()
            
            return result
        except Exception as e:
            logger.error(f"注册失败: {e}")
            raise
    
    def _download_model(self) -> Dict:
        """下载全局模型"""
        try:
            response = requests.get(
                f"{self.server_url}/api/global-model/download/{self.client_id}"
            )
            response.raise_for_status()
            result = response.json()
            
            model_info = result['model']
            self.current_model = model_info['model_params']
            self.current_version = model_info['version_id']
            
            # 保存到本地
            model_file = self.local_data_dir / f"model_{self.current_version}.json"
            with open(model_file, 'w') as f:
                json.dump(model_info, f, indent=2)
            
            logger.info(f"模型已下载: {self.current_version}")
            
            return model_info
        except Exception as e:
            logger.error(f"下载模型失败: {e}")
            raise
    
    def load_private_data(self, data_source: str) -> int:
        """
        加载本地私有数据
        
        Args:
            data_source: 数据源路径
        
        Returns:
            数据数量
        """
        try:
            # 加载私有数据(实际应该从数据库/文件系统读取)
            # 这里简化为JSON文件
            with open(data_source, 'r', encoding='utf-8') as f:
                self.private_data = json.load(f)
            
            logger.info(f"已加载{len(self.private_data)}条私有数据")
            
            return len(self.private_data)
        except Exception as e:
            logger.error(f"加载私有数据失败: {e}")
            raise
    
    def build_local_rag(self) -> Dict:
        """
        构建本地私有RAG知识库
        
        Returns:
            RAG构建结果
        """
        try:
            from app.services.ragservice import RAGService
            
            # 创建本地RAG实例
            self.local_rag = RAGService(
                data_dir=str(self.local_data_dir / "rag"),
                use_vector_db=True
            )
            
            # 处理私有数据并构建知识库
            for item in self.private_data:
                if 'text' in item:
                    # 上传文档到RAG
                    self.local_rag.upload_document(
                        file_data=item['text'].encode(),
                        filename=item.get('filename', 'document.txt'),
                        metadata=item.get('metadata', {})
                    )
            
            logger.info(f"本地RAG知识库已构建,文档数: {len(self.local_rag.documents)}")
            
            return {
                'success': True,
                'documents_count': len(self.local_rag.documents),
                'index_size': len(self.local_rag.index)
            }
        except Exception as e:
            logger.error(f"构建本地RAG失败: {e}")
            raise
    
    def train_local_model(
        self,
        epochs: int = 5,
        learning_rate: float = 0.001
    ) -> Dict:
        """
        在本地私有数据上训练模型
        
        Args:
            epochs: 训练轮次
            learning_rate: 学习率
        
        Returns:
            训练结果
        """
        if not self.current_model:
            raise ValueError("未加载全局模型,请先下载")
        
        if not self.private_data:
            raise ValueError("未加载私有数据")
        
        logger.info(f"开始本地训练,数据量: {len(self.private_data)}, epochs: {epochs}")
        
        # 这里简化实现:实际应该调用真实的训练流程
        # 示例:使用通义千问API进行few-shot学习
        
        # 1. 提取训练样本
        training_samples = [
            {
                'input': item.get('input', ''),
                'output': item.get('output', '')
            }
            for item in self.private_data
            if 'input' in item and 'output' in item
        ]
        
        # 2. 模拟训练(实际应该调用模型训练API)
        trained_model = self._simulate_training(
            base_model=self.current_model,
            training_data=training_samples,
            epochs=epochs,
            learning_rate=learning_rate
        )
        
        # 3. 提取参数更新
        param_updates = self._extract_parameter_updates(
            old_model=self.current_model,
            new_model=trained_model
        )
        
        logger.info("本地训练完成")
        
        return {
            'success': True,
            'param_updates': param_updates,
            'training_samples': len(training_samples),
            'epochs': epochs
        }
    
    def _simulate_training(
        self,
        base_model: Dict,
        training_data: List[Dict],
        epochs: int,
        learning_rate: float
    ) -> Dict:
        """
        模拟训练过程
        
        实际实现应该:
        1. 加载基础模型
        2. 在本地数据上微调
        3. 返回更新后的模型
        
        这里简化为添加少量随机扰动
        """
        import numpy as np
        
        trained_model = {}
        for key, value in base_model.items():
            if isinstance(value, list):
                # 添加少量随机更新(实际应该是真实的梯度更新)
                update = np.random.randn(*np.array(value).shape) * learning_rate
                trained_model[key] = (np.array(value) + update).tolist()
            else:
                trained_model[key] = value
        
        return trained_model
    
    def _extract_parameter_updates(
        self,
        old_model: Dict,
        new_model: Dict
    ) -> Dict:
        """提取参数更新(新模型 - 旧模型)"""
        import numpy as np
        
        updates = {}
        for key in old_model.keys():
            if isinstance(old_model[key], list):
                updates[key] = (
                    np.array(new_model[key]) - np.array(old_model[key])
                ).tolist()
            else:
                updates[key] = new_model[key]
        
        return updates
    
    def upload_update(
        self,
        param_updates: Dict,
        metadata: Dict
    ) -> Dict:
        """
        上传参数更新到服务器
        
        Args:
            param_updates: 参数更新
            metadata: 元数据(训练信息)
        
        Returns:
            上传结果
        """
        try:
            # 1. 添加差分隐私
            from app.services.encryptionservice import encryption_service
            noisy_updates = encryption_service.add_differential_privacy(
                parameters=param_updates,
                epsilon=1.0,
                delta=1e-5
            )
            
            # 2. 加密参数
            encrypted_updates = encryption_service.encrypt_parameters(
                parameters=noisy_updates
            )
            
            # 3. 上传到服务器
            response = requests.post(
                f"{self.server_url}/api/global-model/upload-update",
                json={
                    'client_id': self.client_id,
                    'encrypted_update': encrypted_updates,
                    'update_metadata': {
                        **metadata,
                        'data_size': len(self.private_data),
                        'upload_time': datetime.now().isoformat()
                    }
                }
            )
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"参数更新已上传,待聚合数: {result.get('pending_updates_count')}")
            
            return result
        except Exception as e:
            logger.error(f"上传参数更新失败: {e}")
            raise
    
    def sync_global_model(self) -> Dict:
        """
        同步全局模型
        
        检查并下载新版本的全局模型
        """
        try:
            # 下载最新全局模型
            new_model = self._download_model()
            
            if new_model['version_id'] != self.current_version:
                logger.info(f"全局模型已更新: {self.current_version} -> {new_model['version_id']}")
                return {
                    'updated': True,
                    'old_version': self.current_version,
                    'new_version': new_model['version_id']
                }
            else:
                logger.info("全局模型未更新")
                return {
                    'updated': False,
                    'version': self.current_version
                }
        except Exception as e:
            logger.error(f"同步全局模型失败: {e}")
            raise
    
    def complete_training_cycle(
        self,
        epochs: int = 5,
        learning_rate: float = 0.001
    ) -> Dict:
        """
        完成一个完整的训练周期
        
        1. 下载全局模型
        2. 本地训练
        3. 上传参数更新
        4. 等待聚合
        5. 同步新模型
        
        Args:
            epochs: 训练轮次
            learning_rate: 学习率
        
        Returns:
            训练周期结果
        """
        results = {}
        
        # 1. 同步全局模型
        sync_result = self.sync_global_model()
        results['sync'] = sync_result
        
        # 2. 本地训练
        train_result = self.train_local_model(epochs=epochs, learning_rate=learning_rate)
        results['training'] = train_result
        
        # 3. 上传参数更新
        upload_result = self.upload_update(
            param_updates=train_result['param_updates'],
            metadata={
                'epochs': epochs,
                'learning_rate': learning_rate,
                'training_samples': train_result['training_samples']
            }
        )
        results['upload'] = upload_result
        
        logger.info("训练周期完成")
        
        return {
            'success': True,
            'client_id': self.client_id,
            'cycle_results': results,
            'timestamp': datetime.now().isoformat()
        }
```

*由于内容过长,继续在下一个文件中编写...*

