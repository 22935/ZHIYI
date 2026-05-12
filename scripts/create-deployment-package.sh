#!/bin/bash

# 创建部署包（不包含Docker镜像，仅配置文件）
# 适用于已有Docker环境的快速部署

set -e

PROJECT_DIR=$(cd "$(dirname "$0")/.." && pwd)
VERSION=${1:-"latest"}
PACKAGE_DIR="$PROJECT_DIR/deployment-package/kinlin-ai-$VERSION"
BUILD_DATE=$(date +%Y%m%d_%H%M%S)

echo "=========================================="
echo "创建联邦智枢部署包"
echo "版本: $VERSION"
echo "=========================================="

# 创建目录
rm -rf "$PACKAGE_DIR"
mkdir -p "$PACKAGE_DIR"/{docker,config,scripts}

# 1. 复制Docker Compose配置
echo "复制Docker配置..."
cp docker/docker-compose.prod.yml "$PACKAGE_DIR/docker/"
cp docker/docker-compose.yml "$PACKAGE_DIR/docker/" 2>/dev/null || true

# 2. 创建配置模板
echo "创建配置模板..."
cat > "$PACKAGE_DIR/config/.env.template" << 'EOF'
# ============================================
# 联邦智枢 环境配置
# ============================================

# 数据库配置
DB_USERNAME=kinlin_ai
DB_PASSWORD=请修改为强密码（至少16位）
REDIS_PASSWORD=请修改为强密码（至少16位）

# 麒麟AI API配置（必需）
KYLIN_AI_API_KEY=请填写您的麒麟AI API密钥
KYLIN_AI_ENDPOINT=https://api.kylin.ai
KYLIN_AI_TIMEOUT=30

# 应用配置
SPRING_PROFILES_ACTIVE=prod
ENVIRONMENT=production
LOG_LEVEL=INFO

# JWT配置（可选）
APP_JWT_SECRET=请修改为至少64字符的随机字符串（用于JWT令牌签名）
EOF

# 3. 创建快速部署脚本
cat > "$PACKAGE_DIR/deploy.sh" << 'SCRIPT_EOF'
#!/bin/bash

# 联邦智枢 快速部署脚本

set -e

echo "=========================================="
echo "联邦智枢 快速部署"
echo "=========================================="

# 检查Docker
if ! command -v docker &> /dev/null; then
    echo "错误: 未安装Docker，请先安装Docker"
    exit 1
fi

# 检查Docker Compose
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "错误: 未安装Docker Compose"
    exit 1
fi

# 获取脚本目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 1. 配置环境变量
if [ ! -f .env ]; then
    echo "创建.env配置文件..."
    cp config/.env.template .env
    echo ""
    echo "=========================================="
    echo "⚠️  请编辑 .env 文件，配置以下必需项:"
    echo "   - DB_PASSWORD: 数据库密码"
    echo "   - REDIS_PASSWORD: Redis密码"
    echo "   - KYLIN_AI_API_KEY: 麒麟AI API密钥"
    echo "=========================================="
    echo ""
    read -p "配置完成后按Enter继续，或按Ctrl+C取消..."
fi

# 2. 构建镜像（如果需要）
echo "检查Docker镜像..."
if ! docker images | grep -q "kinlin-ai-backend"; then
    echo "未找到Docker镜像，需要构建..."
    echo "请确保在项目源码目录运行构建，或使用预构建的镜像"
    read -p "是否现在构建镜像？(y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "构建镜像..."
        # 这里需要项目源码，暂时跳过
        echo "请手动构建镜像或使用预构建镜像"
    fi
fi

# 3. 启动服务
echo "启动服务..."
cd docker

# 使用docker-compose或docker compose
if command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
else
    COMPOSE_CMD="docker compose"
fi

$COMPOSE_CMD -f docker-compose.prod.yml pull 2>/dev/null || true
$COMPOSE_CMD -f docker-compose.prod.yml up -d

# 4. 等待服务启动
echo "等待服务启动..."
sleep 15

# 5. 检查服务状态
echo ""
echo "=========================================="
echo "服务状态:"
echo "=========================================="
$COMPOSE_CMD -f docker-compose.prod.yml ps

# 6. 健康检查
echo ""
echo "健康检查..."
if curl -f -s http://localhost:8090/health > /dev/null 2>&1; then
    echo "✓ 后端服务正常"
else
    echo "✗ 后端服务异常"
fi

if curl -f -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "✓ AI服务正常"
else
    echo "✗ AI服务异常"
fi

echo ""
echo "=========================================="
echo "部署完成！"
echo "=========================================="
echo ""
echo "访问地址:"
echo "  前端: http://$(hostname -I | awk '{print $1}')"
echo "  后端: http://$(hostname -I | awk '{print $1}'):8090/health"
echo ""
echo "常用命令:"
echo "  查看日志: cd docker && $COMPOSE_CMD -f docker-compose.prod.yml logs -f"
echo "  停止服务: cd docker && $COMPOSE_CMD -f docker-compose.prod.yml down"
echo "  重启服务: cd docker && $COMPOSE_CMD -f docker-compose.prod.yml restart"
echo ""
SCRIPT_EOF

chmod +x "$PACKAGE_DIR/deploy.sh"

# 4. 创建README
cat > "$PACKAGE_DIR/README.md" << 'EOF'
# 联邦智枢 部署包

## 快速开始

### 前提条件

1. 已安装Docker和Docker Compose
2. 已准备好麒麟AI API密钥

### 部署步骤

1. **解压部署包**
   ```bash
   tar -xzf kinlin-ai-*.tar.gz
   cd kinlin-ai-*
   ```

2. **配置环境变量**
   ```bash
   cp config/.env.template .env
   vim .env  # 编辑配置文件
   ```

3. **运行部署脚本**
   ```bash
   chmod +x deploy.sh
   ./deploy.sh
   ```

4. **访问系统**
   - 前端: http://服务器IP
   - 后端API: http://服务器IP:8090

## 配置说明

必须配置以下项：

- `DB_PASSWORD`: 数据库密码（至少16位）
- `REDIS_PASSWORD`: Redis密码（至少16位）
- `KYLIN_AI_API_KEY`: 麒麟AI API密钥

## 管理命令

```bash
# 进入docker目录
cd docker

# 查看日志
docker-compose -f docker-compose.prod.yml logs -f

# 停止服务
docker-compose -f docker-compose.prod.yml down

# 重启服务
docker-compose -f docker-compose.prod.yml restart

# 更新服务
docker-compose -f docker-compose.prod.yml pull
docker-compose -f docker-compose.prod.yml up -d
```

## 故障排查

1. **服务无法启动**: 检查`.env`配置是否正确
2. **无法访问**: 检查防火墙端口是否开放
3. **查看日志**: `cd docker && docker-compose -f docker-compose.prod.yml logs`

## 详细文档

更多信息请查看: `docs/麒麟操作系统部署指南.md`
EOF

# 5. 创建压缩包
echo "创建压缩包..."
cd "$PROJECT_DIR/deployment-package"
tar -czf "kinlin-ai-deploy-$VERSION-$BUILD_DATE.tar.gz" "kinlin-ai-$VERSION"

echo ""
echo "=========================================="
echo "部署包创建完成！"
echo "=========================================="
echo "位置: $PROJECT_DIR/deployment-package/kinlin-ai-deploy-$VERSION-$BUILD_DATE.tar.gz"
echo ""
echo "使用方法:"
echo "  1. 将压缩包上传到服务器"
echo "  2. 解压: tar -xzf kinlin-ai-deploy-*.tar.gz"
echo "  3. 配置: 编辑 .env 文件"
echo "  4. 部署: ./deploy.sh"
echo ""

