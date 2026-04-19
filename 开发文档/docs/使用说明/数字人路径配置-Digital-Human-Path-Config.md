# 数字人图像和数据路径配置说明

## 修复日期
2026-01-03

## 问题描述
1. **图像路径不一致**：代码中使用的路径与实际文件存储路径不匹配
2. **数据保存/加载路径不一致**：保存和加载使用不同的路径
3. **文件名格式不匹配**：实际文件名包含时间戳，但代码查找固定格式

## 修复后的路径结构

### 文件系统路径（相对于 `agent/` 目录）
```
agent/
└── data/
    └── digital-human/
        ├── images/
        │   └── realistic/
        │       └── {role_id}_{timestamp}.png  # 例如: eb1f87f8-bb20-4de4-8cb7-9251a472576a_20260103_004702.png
        └── metadata/
            └── {role_id}.json  # 例如: eb1f87f8-bb20-4de4-8cb7-9251a472576a.json
```

### API访问路径
- **图像URL**：`/api/static/digital-human/images/realistic/{filename}`
  - 映射到：`agent/data/digital-human/images/realistic/{filename}`
- **静态文件服务**：挂载在 `/api/static`，指向 `agent/data` 目录

## 代码配置

### 1. 图像保存目录
```python
# agent/app/services/digitalhumanservice.py
self.avatar_image_dir = Path("data/digital-human/images/realistic")
```

### 2. 数据保存/加载目录
```python
# 保存
data_dir = Path("data/digital-human/metadata")
file_path = data_dir / f"{role_id}.json"

# 加载
data_dir = Path("data/digital-human/metadata")
file_path = data_dir / f"{role_id}.json"
```

### 3. 图像URL生成
```python
# 所有图像URL统一使用此格式
local_image_url = f"/api/static/digital-human/images/realistic/{image_file.name}"
```

### 4. 文件名格式
- **图像文件**：`{role_id}_{timestamp}.png`
  - 时间戳格式：`YYYYMMDD_HHMMSS`
  - 例如：`eb1f87f8-bb20-4de4-8cb7-9251a472576a_20260103_004702.png`
- **数据文件**：`{role_id}.json`
  - 例如：`eb1f87f8-bb20-4de4-8cb7-9251a472576a.json`

### 5. 文件查找逻辑
- 使用 `glob` 模式查找图像文件：`{role_id}_*.png`
- 支持带时间戳的文件名
- 如果找到已存在的文件，跳过生成

## 静态文件服务配置

### main.py 中的配置
```python
# 注册静态文件服务（用于访问数字人图像）
_project_root = Path(__file__).resolve().parent.parent.parent
_data_dir = _project_root / "agent" / "data"
if _data_dir.exists():
    app.mount("/api/static", StaticFiles(directory=str(_data_dir)), name="static")
    logger.info(f"静态文件服务已注册: {_data_dir}")
```

## 修复内容总结

### 1. 统一数据保存/加载路径
- **修复前**：
  - 保存：`data/digital-human/data/{role_id}.json`
  - 加载：`data/digital-human/data/images/metadata/{role_id}.json`
- **修复后**：
  - 保存：`data/digital-human/metadata/{role_id}.json`
  - 加载：`data/digital-human/metadata/{role_id}.json`

### 2. 统一图像路径
- **修复前**：`static/digital-human/images/`
- **修复后**：`data/digital-human/images/realistic/`

### 3. 统一图像URL
- **修复前**：`/static/digital-human/images/{filename}`
- **修复后**：`/api/static/digital-human/images/realistic/{filename}`

### 4. 支持带时间戳的文件名
- 使用 `glob` 模式 `{role_id}_*.png` 查找文件
- 保存新图像时自动添加时间戳

## 验证方法

### 1. 检查文件是否存在
```bash
# 图像文件
ls agent/data/digital-human/images/realistic/

# 元数据文件
ls agent/data/digital-human/metadata/
```

### 2. 测试API访问
```bash
# 测试图像URL（替换为实际文件名）
curl http://localhost:8000/api/static/digital-human/images/realistic/{filename}

# 测试数字人API
curl http://localhost:8000/ai/digital-human/{role_id}
```

### 3. 检查日志
- 查看日志中是否有路径相关的错误
- 确认图像和数据文件保存/加载成功

## 注意事项

1. **路径一致性**：确保所有代码中的路径配置一致
2. **目录创建**：代码会自动创建不存在的目录
3. **文件查找**：使用 `glob` 模式支持带时间戳的文件名
4. **静态文件服务**：确保 `/api/static` 正确挂载到 `agent/data` 目录
5. **避免重复生成**：代码会检查文件是否存在，避免重复生成

## 相关文件

- `agent/app/services/digitalhumanservice.py` - 数字人服务主文件
- `agent/app/main.py` - FastAPI应用主文件，配置静态文件服务
- `agent/data/digital-human/` - 实际文件存储目录

