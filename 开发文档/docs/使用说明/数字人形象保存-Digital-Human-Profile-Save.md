# 数字人形象保存说明

## 📁 保存路径

数字人形象数据保存在以下目录结构中：

```
agent/
└── data/
    └── digital-human/
        ├── images/              # 图像文件目录
        │   ├── realistic/       # 写实风格图像
        │   ├── cartoon/         # 卡通风格图像
        │   └── anime/          # 二次元风格图像
        └── metadata/           # 元数据JSON文件
            └── {role_id}.json  # 每个角色的元数据
```

### 完整路径示例

**Windows系统：**
```
E:\Project\Kinlin_AI\agent\data\digital-human\images\realistic\{role_id}_{timestamp}.png
E:\Project\Kinlin_AI\agent\data\digital-human\metadata\{role_id}.json
```

**Linux/Mac系统：**
```
/path/to/project/agent/data/digital-human/images/realistic/{role_id}_{timestamp}.png
/path/to/project/agent/data/digital-human/metadata/{role_id}.json
```

## 🔢 编号系统

### 图像编号格式

图像文件使用以下编号格式：
```
{role_id}_{YYYYMMDD}_{HHMMSS}.png
```

**示例：**
- `eb1f87f8-bb20-4de4-8cb7-9251a472576a_20260103_002722.png`
- `30ce9ee6-1bf9-4f83-b7d6-b242a94555d4_20260103_002815.png`

### 编号组成部分

1. **role_id**: 角色唯一标识符（UUID格式）
2. **timestamp**: 生成时间戳（格式：YYYYMMDD_HHMMSS）
   - `YYYYMMDD`: 年月日（如：20260103）
   - `HHMMSS`: 时分秒（如：002722）

### 编号特点

- ✅ **唯一性**: 每个图像都有唯一的编号
- ✅ **可追溯**: 通过编号可以知道生成时间
- ✅ **可排序**: 按时间顺序排列
- ✅ **易识别**: 包含角色ID，便于管理

## 💾 保存内容

### 1. 图像文件

- **格式**: PNG
- **位置**: `agent/data/digital-human/images/{style}/{image_number}.png`
- **内容**: 数字人形象图像（从AI生成服务下载保存）

### 2. 元数据文件

- **格式**: JSON
- **位置**: `agent/data/digital-human/metadata/{role_id}.json`
- **内容**: 包含以下信息
  ```json
  {
    "role_id": "角色ID",
    "style": "风格（realistic/cartoon/anime）",
    "modelUrl": "3D模型URL",
    "image_path": "图像文件路径",
    "image_url": "图像访问URL",
    "image_number": "图像编号",
    "image_prompt": "生成提示词",
    "status": "状态（ready/default）",
    "created_at": "创建时间",
    "avatar": { /* 数字人配置 */ },
    "expressions": { /* 表情库 */ },
    "animations": { /* 动画库 */ },
    "saved_at": "保存时间"
  }
  ```

## 🌐 访问方式

### 1. 通过API访问

**获取数字人信息（包含图像URL）：**
```
GET /api/ai/digital-human/{role_id}
```

**列出角色的所有图像：**
```
GET /api/ai/digital-human/{role_id}/images?style=realistic
```

**列出所有数字人图像：**
```
GET /api/ai/digital-human/images/all?style=realistic
```

### 2. 通过静态文件服务访问

图像文件可以通过静态文件服务直接访问：
```
GET /api/static/digital-human/images/{style}/{image_number}.png
```

**示例：**
```
GET /api/static/digital-human/images/realistic/eb1f87f8-bb20-4de4-8cb7-9251a472576a_20260103_002722.png
```

## 🔧 功能特性

### ✅ 已实现功能

1. **自动保存**: 生成数字人时自动保存图像和元数据
2. **编号系统**: 基于角色ID和时间戳的唯一编号
3. **风格分类**: 按风格（realistic/cartoon/anime）分类存储
4. **元数据管理**: JSON格式的元数据文件
5. **文件访问**: 通过API和静态文件服务访问
6. **列表查询**: 支持查询角色的所有图像

### 📋 API接口

#### 1. 创建数字人（自动保存）
```http
POST /api/ai/digital-human/create
Content-Type: application/json

{
  "role_id": "eb1f87f8-bb20-4de4-8cb7-9251a472576a",
  "personality": "严谨、专业",
  "profession": "律师",
  "style": "realistic"
}
```

**响应：**
```json
{
  "success": true,
  "data": {
    "role_id": "eb1f87f8-bb20-4de4-8cb7-9251a472576a",
    "image_url": "/api/static/digital-human/images/realistic/eb1f87f8-bb20-4de4-8cb7-9251a472576a_20260103_002722.png",
    "image_path": "E:\\Project\\Kinlin_AI\\agent\\data\\digital-human\\images\\realistic\\eb1f87f8-bb20-4de4-8cb7-9251a472576a_20260103_002722.png",
    "image_number": "eb1f87f8-bb20-4de4-8cb7-9251a472576a_20260103_002722",
    "style": "realistic",
    "status": "ready"
  }
}
```

#### 2. 列出角色的所有图像
```http
GET /api/ai/digital-human/{role_id}/images?style=realistic
```

**响应：**
```json
{
  "success": true,
  "count": 3,
  "data": [
    {
      "file_path": "E:\\Project\\Kinlin_AI\\agent\\data\\digital-human\\images\\realistic\\eb1f87f8-bb20-4de4-8cb7-9251a472576a_20260103_002722.png",
      "relative_path": "digital-human/images/realistic/eb1f87f8-bb20-4de4-8cb7-9251a472576a_20260103_002722.png",
      "local_url": "/api/static/digital-human/images/realistic/eb1f87f8-bb20-4de4-8cb7-9251a472576a_20260103_002722.png",
      "role_id": "eb1f87f8-bb20-4de4-8cb7-9251a472576a",
      "image_number": "eb1f87f8-bb20-4de4-8cb7-9251a472576a_20260103_002722",
      "style": "realistic",
      "created_at": "2026-01-03T00:27:22",
      "size": 245678
    }
  ]
}
```

#### 3. 列出所有数字人图像
```http
GET /api/ai/digital-human/images/all?style=realistic
```

## 📝 使用示例

### Python代码示例

```python
# 创建数字人（自动保存）
import httpx

async with httpx.AsyncClient() as client:
    response = await client.post(
        "http://localhost:8000/ai/digital-human/create",
        json={
            "role_id": "eb1f87f8-bb20-4de4-8cb7-9251a472576a",
            "personality": "严谨、专业",
            "profession": "律师",
            "style": "realistic"
        }
    )
    result = response.json()
    print(f"图像已保存: {result['data']['image_path']}")
    print(f"图像编号: {result['data']['image_number']}")

# 列出角色的所有图像
response = await client.get(
    "http://localhost:8000/ai/digital-human/eb1f87f8-bb20-4de4-8cb7-9251a472576a/images"
)
images = response.json()["data"]
for img in images:
    print(f"图像编号: {img['image_number']}, 创建时间: {img['created_at']}")
```

## 🔍 文件管理

### 查看保存的文件

**Windows PowerShell:**
```powershell
# 查看所有图像
Get-ChildItem -Path "agent\data\digital-human\images" -Recurse -Filter "*.png"

# 查看特定角色的图像
Get-ChildItem -Path "agent\data\digital-human\images" -Recurse -Filter "{role_id}_*.png"

# 查看元数据
Get-ChildItem -Path "agent\data\digital-human\metadata" -Filter "*.json"
```

**Linux/Mac:**
```bash
# 查看所有图像
find agent/data/digital-human/images -name "*.png"

# 查看特定角色的图像
find agent/data/digital-human/images -name "{role_id}_*.png"

# 查看元数据
ls agent/data/digital-human/metadata/*.json
```

## ⚠️ 注意事项

1. **存储空间**: 图像文件会占用磁盘空间，建议定期清理不需要的图像
2. **备份**: 重要数据建议定期备份 `agent/data/digital-human` 目录
3. **权限**: 确保应用有读写 `agent/data/digital-human` 目录的权限
4. **路径**: 路径是相对于项目根目录的，确保在正确的目录下运行应用

## 🚀 未来扩展

计划中的功能：
- [ ] 图像压缩和优化
- [ ] 图像版本管理
- [ ] 批量导出功能
- [ ] 图像搜索和过滤
- [ ] 自动清理旧图像

