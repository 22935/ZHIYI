#!/bin/bash

echo ""
echo "========================================"
echo "  联邦智枢 快速修复工具"
echo "========================================"
echo ""
echo "此工具将自动修复以下问题:"
echo "  1. Pydantic 命名空间警告"
echo "  2. ChromaDB 版本兼容性"
echo ""
echo "========================================"
echo ""

# 检查Python
echo "[1/4] 检查 Python 环境..."
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo "❌ 错误: 未找到 Python"
    echo "   请确保 Python 已安装"
    exit 1
fi

# 使用python3或python
PYTHON_CMD="python3"
if ! command -v python3 &> /dev/null; then
    PYTHON_CMD="python"
fi

echo "✓ Python 环境正常"
echo ""

# 更新ChromaDB
echo "[2/4] 更新 ChromaDB 到稳定版本..."
$PYTHON_CMD -m pip install chromadb==0.4.15 --quiet
if [ $? -eq 0 ]; then
    echo "✓ ChromaDB 已更新"
else
    echo "⚠️  警告: ChromaDB 更新失败，继续执行"
fi
echo ""

# 运行修复脚本
echo "[3/4] 运行 ChromaDB 修复脚本..."
$PYTHON_CMD fix_chromadb.py
if [ $? -eq 0 ]; then
    echo "✓ ChromaDB 修复完成"
else
    echo "⚠️  警告: 修复脚本执行失败"
    echo "   您可以手动删除 app/data/rag/chroma_db 目录"
fi
echo ""

# 清理缓存
echo "[4/4] 清理 Python 缓存..."
find . -type d -name __pycache__ -exec rm -r {} + 2>/dev/null
find . -type f -name "*.pyc" -delete 2>/dev/null
echo "✓ 缓存已清理"
echo ""

echo "========================================"
echo "  修复完成！"
echo "========================================"
echo ""
echo "接下来:"
echo "  1. 重新启动服务: $PYTHON_CMD app/main.py"
echo "  2. 查看日志确认问题已解决"
echo ""
echo "如有问题，请查看:"
echo "  docs/问题修复指南-ChromaDB和Pydantic.md"
echo ""

