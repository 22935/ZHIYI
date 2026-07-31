@echo off
REM 开发环境快速配置脚本 (Windows)
REM 自动创建.env文件并配置开发环境

cd /d %~dp0\..
set PROJECT_DIR=%CD%

echo ==========================================
echo 联邦智枢 开发环境配置
echo ==========================================

REM 1. 创建.env文件（如果不存在）
if not exist .env (
    echo 创建.env配置文件...
    copy .env.example .env
    echo ✓ .env文件已创建
) else (
    echo ✓ .env文件已存在
)

REM 2. 创建agent/.env文件（Python服务）
if not exist agent\.env (
    echo 创建agent/.env配置文件...
    (
        echo # Python AI服务配置
        echo KYLIN_AI_API_KEY=
        echo KYLIN_AI_ENDPOINT=https://api.kylin.ai
        echo KYLIN_AI_TIMEOUT=30
        echo DEBUG=True
        echo LOG_LEVEL=INFO
    ) > agent\.env
    echo ✓ agent/.env文件已创建
) else (
    echo ✓ agent/.env文件已存在
)

echo.
echo ==========================================
echo 配置完成！
echo ==========================================
echo.
echo 配置文件位置:
echo   - 项目根目录: %PROJECT_DIR%\.env
echo   - Python服务: %PROJECT_DIR%\agent\.env
echo.
echo 下一步:
echo   1. 如需使用真实API，请编辑 .env 文件设置 KYLIN_AI_API_KEY
echo   2. 构建并启动全部服务: powershell -ExecutionPolicy Bypass -File dev.ps1 up
echo   3. 查看日志: powershell -ExecutionPolicy Bypass -File dev.ps1 logs
echo   4. 停止服务: powershell -ExecutionPolicy Bypass -File dev.ps1 down
echo.

pause

