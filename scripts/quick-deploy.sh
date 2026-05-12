#!/bin/bash

# 快速部署脚本 - 适用于已有Docker环境的服务器
# 自动检测并配置，最小化手动操作

set -e

echo "=========================================="
echo "联邦智枢 快速部署"
echo "=========================================="

# 检查Docker
if ! command -v docker &> /dev/null; then
    echo "正在安装Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl start docker
    systemctl enable docker
fi

# 检查Docker Compose
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "正在安装Docker Compose..."
    apt-get update
    apt-get install -y docker-compose-plugin
fi

# 获取项目目录
PROJECT_DIR=$(cd "$(dirname "$0")/.." && pwd)
cd "$PROJECT_DIR"

# 创建.env文件（如果不存在）
if [ ! -f .env ]; then
    echo "创建.env配置文件..."
    cat > .env << 'EOF'
# 数据库配置
DB_USERNAME=kinlin_ai
DB_PASSWORD=$(openssl rand -base64 24 | tr -d "=+/" | cut -c1-20)
REDIS_PASSWORD=$(openssl rand -base64 24 | tr -d "=+/" | cut -c1-20)

# 麒麟AI API配置
KYLIN_AI_API_KEY=
KYLIN_AI_ENDPOINT=https://api.kylin.ai

# 应用配置
SPRING_PROFILES_ACTIVE=prod
ENVIRONMENT=production
LOG_LEVEL=INFO
EOF
    
    # 生成随机密码
    DB_PASS=$(openssl rand -base64 24 | tr -d "=+/" | cut -c1-20)
    REDIS_PASS=$(openssl rand -base64 24 | tr -d "=+/" | cut -c1-20)
    
    sed -i "s/DB_PASSWORD=.*/DB_PASSWORD=$DB_PASS/" .env
    sed -i "s/REDIS_PASSWORD=.*/REDIS_PASSWORD=$REDIS_PASS/" .env
    
    echo ""
    echo "=========================================="
    echo "配置文件已创建: $PROJECT_DIR/.env"
    echo ""
    echo "⚠️  请设置以下配置:"
    echo "   KYLIN_AI_API_KEY=您的API密钥"
    echo ""
    echo "已自动生成密码:"
    echo "   DB_PASSWORD=$DB_PASS"
    echo "   REDIS_PASSWORD=$REDIS_PASS"
    echo "=========================================="
    echo ""
    read -p "配置API密钥后按Enter继续，或按Ctrl+C取消..."
fi

# 进入docker目录
cd docker

# 使用docker-compose或docker compose
if command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
else
    COMPOSE_CMD="docker compose"
fi

# 构建并启动
echo "构建Docker镜像..."
$COMPOSE_CMD -f docker-compose.prod.yml build

echo "启动服务..."
$COMPOSE_CMD -f docker-compose.prod.yml up -d

echo "等待服务启动..."
sleep 15

# 检查状态
echo ""
echo "服务状态:"
$COMPOSE_CMD -f docker-compose.prod.yml ps

echo ""
echo "=========================================="
echo "部署完成！"
echo "=========================================="
echo "访问: http://$(hostname -I | awk '{print $1}')"
echo ""

