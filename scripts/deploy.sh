#!/bin/bash

# 联邦智枢 部署脚本
# 使用方法: ./deploy.sh [environment]
# environment: dev, prod (默认: dev)

set -e

ENVIRONMENT=${1:-dev}
PROJECT_DIR=$(cd "$(dirname "$0")/.." && pwd)

echo "=========================================="
echo "联邦智枢 部署脚本"
echo "环境: $ENVIRONMENT"
echo "项目目录: $PROJECT_DIR"
echo "=========================================="

# 检查Docker是否安装
if ! command -v docker &> /dev/null; then
    echo "错误: Docker未安装，请先安装Docker"
    exit 1
fi

# 检查Docker Compose是否安装
if ! command -v docker-compose &> /dev/null; then
    echo "错误: Docker Compose未安装，请先安装Docker Compose"
    exit 1
fi

# 选择docker-compose文件
if [ "$ENVIRONMENT" = "prod" ]; then
    COMPOSE_FILE="docker/docker-compose.prod.yml"
    echo "使用生产环境配置"
else
    COMPOSE_FILE="docker/docker-compose.dev.yml"
    echo "使用开发环境配置"
fi

# 进入项目目录
cd "$PROJECT_DIR"

# 停止现有容器
echo "停止现有容器..."
docker-compose -f "$COMPOSE_FILE" down

# 构建镜像
echo "构建Docker镜像..."
docker-compose -f "$COMPOSE_FILE" build --no-cache

# 启动服务
echo "启动服务..."
docker-compose -f "$COMPOSE_FILE" up -d

# 等待服务启动
echo "等待服务启动..."
sleep 10

# 检查服务状态
echo "检查服务状态..."
docker-compose -f "$COMPOSE_FILE" ps

# 显示日志
echo "显示服务日志（按Ctrl+C退出）..."
docker-compose -f "$COMPOSE_FILE" logs -f





