#!/bin/bash

# 联邦智枢 部署脚本
# 使用方法: ./deploy.sh [environment]
# environment: dev, prod (默认: dev)

set -e

ENVIRONMENT=${1:-dev}
PROJECT_DIR=$(cd "$(dirname "$0")/.." && pwd)

if [ "$ENVIRONMENT" = prod ]; then
    echo "Legacy source-tree production deployment is retired." >&2
    echo "Use scripts.release.publish or an architecture-specific P3 offline package." >&2
    exit 64
fi

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

if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
else
    echo "错误: Docker Compose未安装，请先安装Docker Desktop 或 docker compose plugin"
    exit 1
fi

# 唯一基线为根目录 compose.yaml，再按环境叠加差异层。
if [ "$ENVIRONMENT" = "prod" ]; then
    COMPOSE_FILES=(-f compose.yaml -f compose.prod.yaml)
    echo "使用生产环境配置"
else
    COMPOSE_FILES=(-f compose.yaml -f compose.dev.yaml)
    echo "使用开发环境配置"
fi

# 进入项目目录
cd "$PROJECT_DIR"

# 停止现有容器
echo "停止现有容器..."
"${COMPOSE_CMD[@]}" "${COMPOSE_FILES[@]}" down

# 构建镜像
echo "构建Docker镜像..."
"${COMPOSE_CMD[@]}" "${COMPOSE_FILES[@]}" build --no-cache

# 启动服务
echo "启动服务..."
"${COMPOSE_CMD[@]}" "${COMPOSE_FILES[@]}" up -d

# 等待服务启动
echo "等待服务启动..."
sleep 10

# 检查服务状态
echo "检查服务状态..."
"${COMPOSE_CMD[@]}" "${COMPOSE_FILES[@]}" ps

# 显示日志
echo "显示服务日志（按Ctrl+C退出）..."
"${COMPOSE_CMD[@]}" "${COMPOSE_FILES[@]}" logs -f




