# 联邦学习全局最优模型 - 5分钟快速开始

> 最快速度体验"数据不动模型动,参数可用不可见"的创新技术！

---

## 🚀 快速体验（5分钟）

### Step 1: 启动服务器 (30秒)

```bash
# 进入agent目录
cd agent

# 启动AI服务
python app/main.py
```

服务将在 `http://localhost:8000` 启动

### Step 2: 初始化基础模型 (30秒)

打开Python终端，执行：

```python
import requests

# 初始化基础模型
response = requests.post(
    'http://localhost:8000/ai/global-model/initialize',
    json={
        'model_type': 'text_generation',
        'model_params': {'param1': [1.0] * 100},
        'training_data_info': {
            'source': '公开数据',
            'size': 10000,
            'description': '通用知识'
        }
    }
)

print("✅ 基础模型初始化成功!")
print("版本ID:", response.json()['version_id'])
```

### Step 3: 创建客户端A (1分钟)

```python
from app.services.localtrainingmanager import LocalTrainingManager
import json
from pathlib import Path

# 1. 准备测试数据
test_data = [
    {'input': '问题1', 'output': '答案1', 'text': '文档1内容'},
    {'input': '问题2', 'output': '答案2', 'text': '文档2内容'}
]

data_dir = Path('data/test_client_a')
data_dir.mkdir(parents=True, exist_ok=True)

with open(data_dir / 'private_data.json', 'w', encoding='utf-8') as f:
    json.dump(test_data, f, ensure_ascii=False, indent=2)

# 2. 创建客户端A
client_a = LocalTrainingManager(
    client_id='client_a',
    server_url='http://localhost:8000',
    local_data_dir=str(data_dir)
)

# 3. 注册
client_a.register_to_server({
    'name': '客户端A',
    'organization': '测试机构'
})

# 4. 加载数据
client_a.load_private_data(str(data_dir / 'private_data.json'))

# 5. 构建RAG
client_a.build_local_rag()

# 6. 训练
result_a = client_a.complete_training_cycle(epochs=3)

print("✅ 客户端A训练完成!")
```

### Step 4: 创建客户端B和C (1分钟)

```python
# 客户端B
test_data_b = [
    {'input': '问题3', 'output': '答案3', 'text': '文档3内容'},
    {'input': '问题4', 'output': '答案4', 'text': '文档4内容'}
]

data_dir_b = Path('data/test_client_b')
data_dir_b.mkdir(parents=True, exist_ok=True)

with open(data_dir_b / 'private_data.json', 'w', encoding='utf-8') as f:
    json.dump(test_data_b, f, ensure_ascii=False, indent=2)

client_b = LocalTrainingManager(
    client_id='client_b',
    server_url='http://localhost:8000',
    local_data_dir=str(data_dir_b)
)
client_b.register_to_server({'name': '客户端B'})
client_b.load_private_data(str(data_dir_b / 'private_data.json'))
client_b.build_local_rag()
result_b = client_b.complete_training_cycle(epochs=3)

# 客户端C (同上)
test_data_c = [
    {'input': '问题5', 'output': '答案5', 'text': '文档5内容'},
    {'input': '问题6', 'output': '答案6', 'text': '文档6内容'}
]

data_dir_c = Path('data/test_client_c')
data_dir_c.mkdir(parents=True, exist_ok=True)

with open(data_dir_c / 'private_data.json', 'w', encoding='utf-8') as f:
    json.dump(test_data_c, f, ensure_ascii=False, indent=2)

client_c = LocalTrainingManager(
    client_id='client_c',
    server_url='http://localhost:8000',
    local_data_dir=str(data_dir_c)
)
client_c.register_to_server({'name': '客户端C'})
client_c.load_private_data(str(data_dir_c / 'private_data.json'))
client_c.build_local_rag()
result_c = client_c.complete_training_cycle(epochs=3)

print("✅ 三个客户端训练完成!")
```

### Step 5: 云端聚合 (30秒)

```python
# 手动触发聚合
response = requests.post(
    'http://localhost:8000/ai/global-model/aggregate',
    params={'min_clients': 3}
)

result = response.json()
print("✅ 参数聚合完成!")
print(f"新版本: {result['version']}")
print(f"参与客户端: {result['clients_participated']}")
```

### Step 6: 客户端同步新模型 (30秒)

```python
# 客户端同步全局模型
sync_a = client_a.sync_global_model()
sync_b = client_b.sync_global_model()
sync_c = client_c.sync_global_model()

if sync_a['updated']:
    print(f"✅ 客户端A模型已更新: {sync_a['old_version']} -> {sync_a['new_version']}")

print("\n🎉 完成! 三个客户端都获得了全局优化模型!")
print("💡 注意: 各客户端的私有数据始终保密,但都享受到全局智能提升!")
```

### Step 7: RAG联邦优化 (1分钟) ⭐ 业界首创

```python
from app.services.federatedragoptimizer import federated_rag_optimizer

# 客户端A上传RAG统计
federated_rag_optimizer.collect_client_stats(
    client_id='client_a',
    rag_stats={
        'total_queries': 100,
        'avg_retrieval_time': 0.5,
        'optimal_top_k': 7,
        'optimal_threshold': 0.75,
        'retrieval_success_rate': 0.85
    }
)

# 客户端B、C也上传统计（省略...）

# 分析全局模式
analysis = federated_rag_optimizer.analyze_retrieval_patterns()
print("\n📊 检索模式分析:")
print(f"  总查询数: {analysis['total_queries']}")
print(f"  平均成功率: {analysis['avg_success_rate']:.1%}")

# 优化全局参数
result = federated_rag_optimizer.optimize_global_parameters(strategy='balanced')
print("\n⚡ RAG参数优化完成!")
print(f"  最优top_k: {result['params']['top_k']}")
print(f"  最优阈值: {result['params']['similarity_threshold']:.2f}")
print(f"  预期提升: {result['improvement_estimation']['success_rate']['improvement']:.1%}")
```

### Step 8: 查看前端可视化 (1分钟)

```bash
# 启动前端
cd frontend
npm run dev
```

访问: `http://localhost:3000/federated-learning`

查看:
- 📊 客户端统计
- 🌐 联邦网络拓扑
- 📈 模型版本历史
- ⚡ RAG优化控制面板

---

## 🎊 恭喜！

您已经完成了联邦学习全局最优模型的快速体验！

### 您已经学会了

- ✅ 初始化全局模型
- ✅ 注册和管理客户端
- ✅ 本地训练和参数上传
- ✅ 云端参数聚合
- ✅ 模型同步
- ✅ **RAG联邦优化**（业界首创）

### 核心要点

1. **数据不动**: 各客户端的私有数据从未上传
2. **模型动**: 只有模型参数在流动
3. **参数可用不可见**: 差分隐私+加密双重保护
4. **全局最优**: 所有客户端都享受到全局智能提升

---

## 📚 深入学习

### 初学者

→ [创新点说明](../README-联邦学习创新点.md) - 5分钟了解核心价值

### 开发者

→ [使用指南](./联邦学习全局最优模型-使用指南.md) - 完整部署教程

### 架构师

→ [可行性分析与实现方案](./联邦学习全局最优模型-可行性分析与实现方案.md) - 深度技术分析

### 产品经理

→ [总结报告](./联邦学习全局最优模型-总结报告.md) - 商业价值和路线图

---

## ❓ 常见问题

**Q: 真的能保证数据隐私吗？**  
A: 绝对可以！原始数据永远不上传,只上传经过差分隐私和加密处理的参数。即使参数被窃取,也无法反推原始数据。

**Q: 多少个客户端可以开始聚合？**  
A: 默认至少3个客户端,可配置。客户端越多,模型越好（网络效应）。

**Q: RAG联邦优化的创新点是什么？**  
A: 业界首创！只上传RAG统计数据（如检索时间、成功率），不上传原始文档,就能优化全局检索策略。所有客户端都受益！

**Q: 如何验证隐私保护效果？**  
A: 查看测试代码 `test_differential_privacy()` 和 `test_parameter_encryption()`。

---

## 🎯 下一步

1. ✅ 运行完整测试: `pytest agent/tests/test_federated*.py -v`
2. ✅ 查看前端可视化: `http://localhost:3000/federated-learning`
3. ⏳ 准备真实数据进行试点部署

---

**准备好了吗？** 开始你的联邦学习之旅！ 🚀

**需要帮助？** 查看 [使用指南](./联邦学习全局最优模型-使用指南.md) 或 [常见问题](./联邦学习全局最优模型-使用指南.md#6-常见问题)

