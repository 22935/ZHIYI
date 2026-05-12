#!/bin/bash

# 联邦智枢 麒麟操作系统快速部署脚本
# 使用方法: ./deploy-kylin.sh

set -e

echo "=========================================="
echo "联邦智枢 麒麟操作系统部署脚本"
echo "=========================================="

# 检查是否为root用户
if [ "$EUID" -ne 0 ]; then 
    echo "请使用sudo运行此脚本"
    exit 1
fi

# 检查操作系统
if [ ! -f /etc/kylin-release ]; then
    echo "警告: 未检测到麒麟操作系统，继续执行..."
fi

# 1. 安装Docker
echo "=========================================="
echo "步骤 1/5: 检查并安装Docker"
echo "=========================================="

if command -v docker &> /dev/null; then
    echo "Docker已安装: $(docker --version)"
else
    echo "正在安装Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
    
    # 启动Docker服务
    systemctl start docker
    systemctl enable docker
    
    echo "Docker安装完成"
fi

# 2. 安装Docker Compose
echo "=========================================="
echo "步骤 2/5: 检查并安装Docker Compose"
echo "=========================================="

if command -v docker-compose &> /dev/null; then
    echo "Docker Compose已安装: $(docker-compose --version)"
else
    echo "正在安装Docker Compose..."
    # 安装docker-compose-plugin
    apt-get update
    apt-get install -y docker-compose-plugin
    
    # 或使用传统方式
    if ! command -v docker-compose &> /dev/null; then
        curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
        chmod +x /usr/local/bin/docker-compose
    fi
    
    echo "Docker Compose安装完成"
fi

# 3. 配置Docker镜像加速（可选）
echo "=========================================="
echo "步骤 3/5: 配置Docker镜像加速"
echo "=========================================="

if [ ! -f /etc/docker/daemon.json ]; then
    echo "配置Docker镜像加速..."
    mkdir -p /etc/docker
    cat > /etc/docker/daemon.json << EOF
{
  "registry-mirrors": [
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com"
  ],
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF
    systemctl daemon-reload
    systemctl restart docker
    echo "Docker镜像加速配置完成"
else
    echo "Docker配置已存在，跳过"
fi

# 4. 检查项目文件
echo "=========================================="
echo "步骤 4/5: 检查项目文件"
echo "=========================================="

PROJECT_DIR=$(cd "$(dirname "$0")/.." && pwd)
cd "$PROJECT_DIR"

if [ ! -f "docker/docker-compose.prod.yml" ]; then
    echo "错误: 未找到docker-compose.prod.yml文件"
    echo "请确保在项目根目录运行此脚本"
    exit 1
fi

echo "项目目录: $PROJECT_DIR"

# 5. 配置环境变量
echo "=========================================="
echo "步骤 5/5: 配置环境变量"
echo "=========================================="

if [ ! -f ".env" ]; then
    echo "创建.env配置文件..."
    cat > .env << EOF
# 数据库配置
DB_USERNAME=kinlin_ai
DB_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
REDIS_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)

# 麒麟AI API配置（请修改为您的实际API密钥）
KYLIN_AI_API_KEY=your_kylin_ai_api_key_here
KYLIN_AI_ENDPOINT=https://api.kylin.ai

# 应用配置
SPRING_PROFILES_ACTIVE=prod
ENVIRONMENT=production
LOG_LEVEL=INFO
EOF
    echo ".env文件已创建，请编辑并设置KYLIN_AI_API_KEY"
    echo "文件位置: $PROJECT_DIR/.env"
    read -p "是否已配置API密钥？(y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "请编辑.env文件后重新运行此脚本"
        exit 1
    fi
else
    echo ".env文件已存在"
fi

# 6. 启动服务
echo "=========================================="
echo "启动服务..."
echo "=========================================="

cd docker

# 停止现有容器
echo "停止现有容器..."
docker-compose -f docker-compose.prod.yml down 2>/dev/null || true

# 构建镜像
echo "构建Docker镜像（这可能需要几分钟）..."
docker-compose -f docker-compose.prod.yml build

# 启动服务
echo "启动服务..."
docker-compose -f docker-compose.prod.yml up -d

# 等待服务启动
echo "等待服务启动..."
sleep 15

# 检查服务状态
echo "=========================================="
echo "服务状态:"
echo "=========================================="
docker-compose -f docker-compose.prod.yml ps

# 健康检查
echo ""
echo "=========================================="
echo "健康检查:"
echo "=========================================="

echo "检查后端服务..."
if curl -f -s http://localhost:8090/health > /dev/null; then
    echo "✓ 后端服务正常"
else
    echo "✗ 后端服务异常，请查看日志: docker-compose -f docker/docker-compose.prod.yml logs backend"
fi

echo "检查AI服务..."
if curl -f -s http://localhost:8000/health > /dev/null; then
    echo "✓ AI服务正常"
else
    echo "✗ AI服务异常，请查看日志: docker-compose -f docker/docker-compose.prod.yml logs ai-service"
fi

echo ""
echo "=========================================="
echo "部署完成！"
echo "=========================================="
echo ""
echo "访问地址:"
echo "  前端: http://$(hostname -I | awk '{print $1}')"
echo "  后端API: http://$(hostname -I | awk '{print $1}'):8090"
echo "  AI服务: http://$(hostname -I | awk '{print $1}'):8000"
echo ""
echo "常用命令:"
echo "  查看日志: docker-compose -f docker/docker-compose.prod.yml logs -f"
echo "  停止服务: docker-compose -f docker/docker-compose.prod.yml down"
echo "  重启服务: docker-compose -f docker/docker-compose.prod.yml restart"
echo ""
echo "详细文档: docs/麒麟操作系统部署指南.md"
echo ""

