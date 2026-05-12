@echo off
chcp 65001 >nul
echo.
echo ========================================
echo   联邦智枢 快速修复工具
echo ========================================
echo.
echo 此工具将自动修复以下问题:
echo   1. Pydantic 命名空间警告
echo   2. ChromaDB 版本兼容性
echo.
echo ========================================
echo.

echo [1/4] 检查 Python 环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 错误: 未找到 Python
    echo    请确保 Python 已安装并添加到 PATH
    pause
    exit /b 1
)
echo ✓ Python 环境正常
echo.

echo [2/4] 更新 ChromaDB 到稳定版本...
pip install chromadb==0.4.15 --quiet
if errorlevel 1 (
    echo ⚠️  警告: ChromaDB 更新失败，继续执行
) else (
    echo ✓ ChromaDB 已更新
)
echo.

echo [3/4] 运行 ChromaDB 修复脚本...
python fix_chromadb.py
if errorlevel 1 (
    echo ⚠️  警告: 修复脚本执行失败
    echo    您可以手动删除 app\data\rag\chroma_db 目录
) else (
    echo ✓ ChromaDB 修复完成
)
echo.

echo [4/4] 清理 Python 缓存...
for /d /r %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
echo ✓ 缓存已清理
echo.

echo ========================================
echo   修复完成！
echo ========================================
echo.
echo 接下来:
echo   1. 重新启动服务: python app\main.py
echo   2. 查看日志确认问题已解决
echo.
echo 如有问题，请查看:
echo   docs\问题修复指南-ChromaDB和Pydantic.md
echo.
pause

