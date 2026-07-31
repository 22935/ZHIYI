#!/bin/bash

# 开发环境快速配置脚本
# 自动创建.env文件并配置开发环境

set -e

PROJECT_DIR=$(cd "$(dirname "$0")/.." && pwd)
cd "$PROJECT_DIR"

echo "=========================================="
echo "联邦智枢 开发环境配置"
echo "=========================================="

# 1. 创建.env文件（如果不存在）
if [ ! -f .env ]; then
    echo "创建.env配置文件..."
    cp .env.example .env
    echo "✓ .env文件已创建"
else
    echo "✓ .env文件已存在"
fi

# 2. 创建agent/.env文件（Python服务）
if [ ! -f agent/.env ]; then
    echo "创建agent/.env配置文件..."
    cat > agent/.env << EOF
# Python AI服务配置
KYLIN_AI_API_KEY=
KYLIN_AI_ENDPOINT=https://api.kylin.ai
KYLIN_AI_TIMEOUT=30
DEBUG=True
LOG_LEVEL=INFO
EOF
    echo "✓ agent/.env文件已创建"
else
    echo "✓ agent/.env文件已存在"
fi

# 3. 检查数据库连接
echo ""
echo "检查数据库连接..."
if command -v psql &> /dev/null; then
    if PGPASSWORD=ROOT psql -h localhost -U postgres -d kinlin_ai -c "SELECT 1;" &> /dev/null; then
        echo "✓ PostgreSQL数据库连接正常"
    else
        echo "⚠ PostgreSQL数据库未连接，请确保数据库已启动"
        echo "  启动命令: docker compose -f compose.yaml -f compose.dev.yaml up -d postgres"
    fi
else
    echo "⚠ psql命令未找到，跳过数据库检查"
fi

# 4. 检查Redis连接
echo ""
echo "检查Redis连接..."
if command -v redis-cli &> /dev/null; then
    if redis-cli -h localhost ping &> /dev/null; then
        echo "✓ Redis连接正常"
    else
        echo "⚠ Redis未连接，请确保Redis已启动"
        echo "  启动命令: docker compose -f compose.yaml -f compose.dev.yaml up -d redis"
    fi
else
    echo "⚠ redis-cli命令未找到，跳过Redis检查"
fi

# 5. 显示配置信息
echo ""
echo "=========================================="
echo "配置完成！"
echo "=========================================="
echo ""
echo "配置文件位置:"
echo "  - 项目根目录: $PROJECT_DIR/.env"
echo "  - Python服务: $PROJECT_DIR/agent/.env"
echo ""
echo "下一步:"
echo "  1. 如需使用真实API，请编辑 .env 文件设置 KYLIN_AI_API_KEY"
echo "  2. 构建并启动全部服务: ./dev.sh up"
echo "  3. 查看日志: ./dev.sh logs"
echo "  4. 停止服务: ./dev.sh down"
echo ""

