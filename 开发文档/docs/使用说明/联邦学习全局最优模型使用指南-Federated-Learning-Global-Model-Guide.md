# 联邦学习全局最优模型系统 - 使用指南

## 📚 目录

1. [快速开始](#快速开始)
2. [云端服务器配置](#云端服务器配置)
3. [客户端部署](#客户端部署)
4. [完整工作流程示例](#完整工作流程示例)
5. [监控和管理](#监控和管理)
6. [常见问题](#常见问题)

---

## 1. 快速开始

### 1.1 系统要求

**云端服务器**:
- Python 3.8+
- FastAPI
- 8GB+ RAM
- 100GB+ 存储空间

**客户端**:
- Python 3.8+
- 网络连接到云端服务器
- 本地存储空间(根据数据量)

### 1.2 15分钟快速体验

#### Step 1: 启动云端服务器

```bash
# 进入agent目录
cd agent

# 安装依赖(如果还没有)
pip install -r requirements.txt

# 启动AI服务
python app/main.py
```

服务将在 `http://localhost:8000` 启动

#### Step 2: 初始化基础模型

```python
import requests

# 1. 初始化基础模型
response = requests.post(
    'http://localhost:8000/ai/global-model/initialize',
    json={
        'model_type': 'text_generation',
        'model_params': {
            'embedding_dim': 768,
            'hidden_size': 1024,
            'num_layers': 12
        },
        'training_data_info': {
            'source': '公开数据集',
            'size': 1000000,
            'description': '通用领域文本数据'
        }
    }
)

print("基础模型初始化成功:", response.json())
```

#### Step 3: 注册客户端并开始训练

```python
from app.services.localtrainingmanager import LocalTrainingManager

# 1. 创建客户端训练管理器
client = LocalTrainingManager(
    client_id='hospital_a',
    server_url='http://localhost:8000'
)

# 2. 注册到服务器
client.register_to_server({
    'name': 'A医院',
    'organization': '医疗机构',
    'data_scale': 10000
})

# 3. 加载本地私有数据
client.load_private_data('data/hospital_a_private_data.json')

# 4. 构建本地RAG知识库
client.build_local_rag()

# 5. 完成一个训练周期
result = client.complete_training_cycle(epochs=5)

print("训练周期完成:", result)
```

#### Step 4: 云端聚合(当收集到多个客户端更新后)

```python
# 手动触发聚合(通常自动触发)
response = requests.post(
    'http://localhost:8000/ai/global-model/aggregate',
    params={'min_clients': 3}
)

print("聚合完成:", response.json())
```

#### Step 5: 客户端同步新模型

```python
# 客户端同步全局模型
sync_result = client.sync_global_model()

if sync_result['updated']:
    print(f"模型已更新: {sync_result['old_version']} -> {sync_result['new_version']}")
else:
    print("模型未更新")
```

---

## 2. 云端服务器配置

### 2.1 环境变量配置

创建 `.env` 文件:

```bash
# 联邦学习配置
FEDERATED_LEARNING_ENABLED=true
MIN_CLIENTS_FOR_AGGREGATION=3
AGGREGATION_LEARNING_RATE=0.1

# 安全配置
DIFFERENTIAL_PRIVACY_EPSILON=1.0
DIFFERENTIAL_PRIVACY_DELTA=1e-5
ENCRYPTION_KEY=your_secure_encryption_key_here

# 存储配置
GLOBAL_MODEL_STORAGE_DIR=data/global_models
MAX_MODEL_VERSIONS=100

# 服务器配置
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
```

### 2.2 启动服务器

#### 开发模式

```bash
cd agent
python app/main.py
```

#### 生产模式(使用Gunicorn)

```bash
cd agent
gunicorn app.main:app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --timeout 300
```

#### Docker部署

```bash
# 构建镜像
docker build -t kinlin-ai-federated:latest -f Dockerfile .

# 运行容器
docker run -d \
    -p 8000:8000 \
    -v /path/to/data:/app/data \
    -e FEDERATED_LEARNING_ENABLED=true \
    --name kinlin-federated-server \
    kinlin-ai-federated:latest
```

---

## 3. 客户端部署

### 3.1 客户端配置

每个客户端创建配置文件 `client_config.json`:

```json
{
  "client_id": "hospital_a",
  "client_info": {
    "name": "A医院",
    "organization": "医疗机构",
    "location": "北京",
    "contact": "admin@hospital-a.com"
  },
  "server_url": "https://federated-server.example.com",
  "local_data_dir": "data/local_training",
  "training_config": {
    "epochs": 5,
    "learning_rate": 0.001,
    "batch_size": 32,
    "auto_sync_interval": 3600
  },
  "privacy_config": {
    "epsilon": 1.0,
    "delta": 1e-5,
    "enable_encryption": true
  }
}
```

### 3.2 准备本地私有数据

创建 `data/local_training/private_data.json`:

```json
[
  {
    "input": "患者症状：头痛、发热",
    "output": "可能是感冒，建议休息并多喝水",
    "metadata": {
      "category": "常见疾病",
      "date": "2025-01-01"
    }
  },
  {
    "input": "如何预防糖尿病？",
    "output": "控制饮食、定期运动、保持健康体重",
    "metadata": {
      "category": "健康咨询",
      "date": "2025-01-02"
    }
  }
]
```

### 3.3 运行客户端训练脚本

创建 `client_training.py`:

```python
#!/usr/bin/env python3
"""
客户端训练脚本
"""
import json
import logging
import time
from pathlib import Path
from app.services.localtrainingmanager import LocalTrainingManager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config(config_file: str = 'client_config.json') -> dict:
    """加载客户端配置"""
    with open(config_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def main():
    # 1. 加载配置
    config = load_config()
    logger.info(f"客户端配置已加载: {config['client_id']}")
    
    # 2. 创建训练管理器
    trainer = LocalTrainingManager(
        client_id=config['client_id'],
        server_url=config['server_url'],
        local_data_dir=config['local_data_dir']
    )
    
    # 3. 注册到服务器
    try:
        trainer.register_to_server(config['client_info'])
        logger.info("注册成功")
    except Exception as e:
        logger.error(f"注册失败: {e}")
        return
    
    # 4. 加载本地私有数据
    data_file = Path(config['local_data_dir']) / 'private_data.json'
    if data_file.exists():
        data_count = trainer.load_private_data(str(data_file))
        logger.info(f"已加载 {data_count} 条私有数据")
    else:
        logger.warning("私有数据文件不存在，跳过训练")
        return
    
    # 5. 构建本地RAG知识库
    try:
        rag_result = trainer.build_local_rag()
        logger.info(f"RAG知识库已构建: {rag_result}")
    except Exception as e:
        logger.warning(f"构建RAG失败: {e}")
    
    # 6. 训练循环
    training_config = config['training_config']
    auto_sync_interval = training_config.get('auto_sync_interval', 3600)
    
    logger.info("开始训练循环...")
    
    while True:
        try:
            # 完成一个训练周期
            result = trainer.complete_training_cycle(
                epochs=training_config['epochs'],
                learning_rate=training_config['learning_rate']
            )
            
            logger.info(f"训练周期完成: {result['timestamp']}")
            
            # 等待下次训练
            logger.info(f"等待 {auto_sync_interval} 秒后进行下一轮训练...")
            time.sleep(auto_sync_interval)
            
        except KeyboardInterrupt:
            logger.info("训练已停止")
            break
        except Exception as e:
            logger.error(f"训练出错: {e}")
            time.sleep(60)  # 出错后等待1分钟再重试


if __name__ == '__main__':
    main()
```

运行客户端:

```bash
python client_training.py
```

---

## 4. 完整工作流程示例

### 4.1 场景: 3家医院联邦学习

#### 医院A (北京)

```python
# 医院A配置
client_a = LocalTrainingManager(
    client_id='hospital_beijing',
    server_url='https://federated-server.example.com'
)

# 注册
client_a.register_to_server({
    'name': '北京医院',
    'organization': '三甲医院',
    'specialization': '心血管科'
})

# 加载私有数据(心血管病例)
client_a.load_private_data('data/cardiovascular_cases.json')

# 训练
client_a.complete_training_cycle(epochs=10)
```

#### 医院B (上海)

```python
# 医院B配置
client_b = LocalTrainingManager(
    client_id='hospital_shanghai',
    server_url='https://federated-server.example.com'
)

# 注册
client_b.register_to_server({
    'name': '上海医院',
    'organization': '三甲医院',
    'specialization': '肿瘤科'
})

# 加载私有数据(肿瘤病例)
client_b.load_private_data('data/oncology_cases.json')

# 训练
client_b.complete_training_cycle(epochs=10)
```

#### 医院C (广州)

```python
# 医院C配置
client_c = LocalTrainingManager(
    client_id='hospital_guangzhou',
    server_url='https://federated-server.example.com'
)

# 注册
client_c.register_to_server({
    'name': '广州医院',
    'organization': '三甲医院',
    'specialization': '儿科'
})

# 加载私有数据(儿科病例)
client_c.load_private_data('data/pediatrics_cases.json')

# 训练
client_c.complete_training_cycle(epochs=10)
```

#### 云端聚合

```python
import requests

# 当收集到3家医院的参数更新后,云端自动或手动聚合
response = requests.post(
    'https://federated-server.example.com/ai/global-model/aggregate',
    params={'min_clients': 3}
)

result = response.json()
print(f"全局模型已更新: {result['new_version_id']}")
print(f"参与医院: {result['clients_participated']}")
```

#### 效果

- 北京医院获得了肿瘤和儿科的知识增强
- 上海医院获得了心血管和儿科的知识增强
- 广州医院获得了心血管和肿瘤的知识增强
- **但各医院的原始病例数据始终保密**

---

## 5. 监控和管理

### 5.1 查看模型历史

```python
import requests

response = requests.get(
    'http://localhost:8000/ai/global-model/history'
)

history = response.json()['history']

for version in history:
    print(f"版本: {version['version']}")
    print(f"  版本ID: {version['version_id']}")
    print(f"  创建时间: {version['created_at']}")
    print(f"  参与客户端: {version['clients_count']}")
    print()
```

### 5.2 查看客户端统计

```python
response = requests.get(
    'http://localhost:8000/ai/global-model/clients'
)

stats = response.json()['statistics']

print(f"总客户端数: {stats['total_clients']}")
print(f"活跃客户端: {stats['active_clients']}")
print("\n客户端列表:")
for client in stats['clients']:
    print(f"  {client['client_id']}: {client['info']['name']}")
    print(f"    上传次数: {client['upload_count']}")
    print(f"    最后上传: {client['last_upload']}")
```

### 5.3 前端可视化(开发中)

访问 `http://localhost:3000/federated-learning` 查看:

- 📊 全局模型演进曲线
- 🌐 联邦节点网络拓扑
- 📈 各客户端贡献统计
- 🔒 隐私保护状态监控
- ⚡ 实时训练进度

---

## 6. 常见问题

### Q1: 客户端注册失败

**原因**: 
- 服务器未启动
- 网络不通
- 客户端ID重复

**解决**:
```python
# 检查服务器状态
import requests
try:
    response = requests.get('http://localhost:8000/health')
    print("服务器正常:", response.json())
except:
    print("服务器未响应,请检查是否启动")

# 使用唯一的客户端ID
client_id = f"client_{int(time.time())}"
```

### Q2: 参数聚合失败

**原因**: 
- 客户端数量不足
- 参数格式不匹配

**解决**:
```python
# 检查待聚合更新数量
response = requests.get(
    'http://localhost:8000/ai/global-model/clients'
)
active = response.json()['statistics']['active_clients']

if active < 3:
    print(f"活跃客户端不足(当前{active},需要至少3个)")
```

### Q3: 本地训练内存不足

**解决**:
```python
# 减小批次大小
training_config = {
    'epochs': 3,        # 减少epoch
    'learning_rate': 0.001,
    'batch_size': 16    # 减小batch_size
}

result = trainer.complete_training_cycle(**training_config)
```

### Q4: 如何验证隐私保护效果

```python
from app.services.encryptionservice import encryption_service

# 测试差分隐私
original_params = {'weight': [1.0, 2.0, 3.0]}

noisy_params = encryption_service.add_differential_privacy(
    parameters=original_params,
    epsilon=1.0
)

print("原始参数:", original_params)
print("加噪参数:", noisy_params)
print("噪声强度:", sum(abs(o - n) for o, n in zip(
    original_params['weight'], 
    noisy_params['weight']
)))
```

### Q5: 如何回滚到之前的模型版本

```python
# 查看历史版本
response = requests.get(
    'http://localhost:8000/ai/global-model/history'
)
history = response.json()['history']

# 加载指定版本(需要实现版本回滚API)
target_version = history[-2]['version_id']  # 回滚到上一个版本
# 实现回滚逻辑...
```

---

## 7. 最佳实践

### 7.1 数据准备

- ✅ 确保本地数据质量(去重、清洗)
- ✅ 数据格式统一(JSON结构一致)
- ✅ 包含足够的训练样本(建议>1000条)

### 7.2 训练配置

- ✅ 初期使用较小的学习率(0.001-0.01)
- ✅ 逐步增加训练轮次
- ✅ 监控训练损失和性能指标

### 7.3 隐私保护

- ✅ 定期检查隐私预算(ε累积)
- ✅ 启用参数加密
- ✅ 定期审计数据访问日志

### 7.4 性能优化

- ✅ 使用向量数据库加速RAG检索
- ✅ 批量处理训练数据
- ✅ 配置合适的聚合阈值

---

## 8. 进阶功能

### 8.1 自动化训练调度

```python
from apscheduler.schedulers.blocking import BlockingScheduler

scheduler = BlockingScheduler()

# 每天凌晨2点自动训练
@scheduler.scheduled_job('cron', hour=2)
def scheduled_training():
    trainer.complete_training_cycle(epochs=5)
    logger.info("自动训练完成")

scheduler.start()
```

### 8.2 性能监控

```python
import psutil
import time

def monitor_training():
    """监控训练过程的资源使用"""
    start_time = time.time()
    start_memory = psutil.virtual_memory().used
    
    # 执行训练
    result = trainer.complete_training_cycle(epochs=5)
    
    # 统计资源使用
    elapsed = time.time() - start_time
    memory_used = psutil.virtual_memory().used - start_memory
    
    print(f"训练耗时: {elapsed:.2f}秒")
    print(f"内存使用: {memory_used / 1024 / 1024:.2f}MB")
    
    return result
```

### 8.3 故障恢复

```python
def robust_training_loop():
    """带故障恢复的训练循环"""
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            result = trainer.complete_training_cycle(epochs=5)
            logger.info("训练成功")
            retry_count = 0  # 重置重试计数
            break
        except Exception as e:
            retry_count += 1
            logger.error(f"训练失败(第{retry_count}次): {e}")
            
            if retry_count < max_retries:
                wait_time = 2 ** retry_count  # 指数退避
                logger.info(f"等待{wait_time}秒后重试...")
                time.sleep(wait_time)
            else:
                logger.error("达到最大重试次数,训练终止")
```

---

## 总结

联邦学习全局最优模型系统提供了一个完整的**数据不动模型动**的解决方案。通过本指南,您可以:

1. ✅ 快速部署云端服务器和客户端
2. ✅ 理解完整的训练和聚合流程
3. ✅ 监控和管理联邦学习网络
4. ✅ 保护数据隐私的同时共享智能

**下一步**: 
- 查看[可行性分析与实现方案](./联邦学习全局最优模型-可行性分析与实现方案.md)了解技术细节
- 访问API文档了解完整接口说明
- 联系技术支持获取定制化部署方案

