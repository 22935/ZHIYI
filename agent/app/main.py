"""
知弈 - Python AI服务主程序
知弈 - 职业智能体操作系统
提供AI能力：文本生成、语音识别、语音合成
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os
import uvicorn
import logging

from fastapi.exceptions import RequestValidationError
from app.api import chat, tts, agentos_core
from app.paths import APP_DATA_DIR
from app.services.aiservice import AIService
from app.integrations.model_adapter import configure_model_adapter
from app.integrations.tool_adapter import configure_tool_adapter
from app.tools import get_tool_runtime
from app.config import settings
from app.security.internal_auth import (
    InternalServiceAuthMiddleware,
    require_valid_internal_token_configuration,
)
from app.utils.logger import setup_logger
from app.middleware.errorhandler import (
    validation_exception_handler,
    general_exception_handler
)

# 设置日志 - 统一使用INFO级别
logger = setup_logger(level=logging.INFO)
configure_model_adapter()
configure_tool_adapter()

# 生命周期事件处理器
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    if settings.ENVIRONMENT.strip().lower() in {"prod", "production"}:
        require_valid_internal_token_configuration(settings.AI_INTERNAL_TOKEN)
    try:
        warmup = await get_tool_runtime().warmup()
        logger.info("Read-only tool runtime ready: %s", warmup)
    except Exception as exc:
        logger.warning("Read-only tool runtime warmup failed: %s", type(exc).__name__)
    await agentos_core.coordinator.startup()
    try:
        yield
    finally:
        await agentos_core.coordinator.shutdown()
    
        # 关闭时执行 - 简化日志输出
        from app.llm.provider_conversation import close_configured_provider_conversation_store

        await close_configured_provider_conversation_store()

app = FastAPI(
    title="知弈 AI Service",
    description="知弈 - 职业智能体操作系统 Python AI Service",
    version="1.0.0",
    lifespan=lifespan
)
from app.middleware.trace import TraceIdMiddleware

app.add_middleware(InternalServiceAuthMiddleware, token=settings.AI_INTERNAL_TOKEN)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TraceIdMiddleware)

# 注册异常处理器
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# 初始化AI服务
ai_service = AIService()

# 注册路由
app.include_router(chat.router, prefix="/ai", tags=["AI"])
app.include_router(tts.router, prefix="/ai", tags=["TTS"])
app.include_router(agentos_core.router, prefix="/ai", tags=["AgentOSCore"])
if settings.SSE_TEST_MODE:
    from app.api import sse_test
    app.include_router(sse_test.router, prefix="/ai", tags=["SSETest"])

# 注册静态文件服务（用于访问数字人图像和其他数据文件）
_data_dir = APP_DATA_DIR

# 确保目录存在
_data_dir.mkdir(parents=True, exist_ok=True)

# 静态文件服务（仅在主进程中注册一次）
import os
_is_main_process = os.environ.get("RUN_MAIN", "false") != "true"

if _is_main_process:
    try:
        static_files = StaticFiles(
            directory=str(_data_dir),
            html=False,
            check_dir=True
        )
        app.mount("/api/static", static_files, name="static")
        logger.info(f"静态文件服务已注册: {_data_dir}")
    except Exception as e:
        logger.error(f"注册静态文件服务失败: {e}", exc_info=True)

# 创新功能路由
try:
    from app.api import digitalhuman, emotion, rolefusion, knowledgegraph, adaptivelearning, multimodal, aigc, modelselector, performance, realtimeasr, rolestylelearning, collaborativechat, emotiondriven, federateddigitalhuman, digitalhumanmodelselector, kylinos, ragenhanced, communicationoptimizer, performanceoptimizer, federatedmodelmanagement, federatedglobal, federatedrag, voice
    app.include_router(digitalhuman.router, prefix="/ai", tags=["DigitalHuman"])
    app.include_router(emotion.router, prefix="/ai", tags=["Emotion"])
    app.include_router(rolefusion.router, prefix="/ai", tags=["RoleFusion"])
    app.include_router(knowledgegraph.router, prefix="/api", tags=["KnowledgeGraph"])
    app.include_router(adaptivelearning.router, prefix="/ai", tags=["AdaptiveLearning"])
    app.include_router(multimodal.router, prefix="/ai", tags=["Multimodal"])
    app.include_router(aigc.router, prefix="/ai", tags=["AIGC"])
    app.include_router(modelselector.router, prefix="/ai", tags=["ModelSelector"])
    app.include_router(performance.router, prefix="/performance", tags=["Performance"])
    app.include_router(realtimeasr.router, prefix="/ai", tags=["RealtimeASR"])
    app.include_router(rolestylelearning.router, prefix="/ai", tags=["RoleStyleLearning"])
    app.include_router(collaborativechat.router, prefix="/ai", tags=["CollaborativeChat"])
    app.include_router(emotiondriven.router, prefix="/ai", tags=["EmotionDriven"])
    app.include_router(federateddigitalhuman.router, prefix="/ai", tags=["FederatedDigitalHuman"])
    app.include_router(digitalhumanmodelselector.router, prefix="/ai", tags=["DigitalHumanModelSelector"])
    app.include_router(kylinos.router, prefix="/ai", tags=["KylinOS"])
    app.include_router(ragenhanced.router, prefix="/ai", tags=["RAGEnhanced"])
    app.include_router(communicationoptimizer.router, prefix="/ai", tags=["CommunicationOptimizer"])
    app.include_router(performanceoptimizer.router, prefix="/ai", tags=["PerformanceOptimizer"])
    app.include_router(federatedmodelmanagement.router, prefix="/ai", tags=["FederatedModelManagement"])
    app.include_router(federatedglobal.router, prefix="/ai", tags=["FederatedGlobal"])
    app.include_router(federatedrag.router, prefix="/ai", tags=["FederatedRAG"])
    app.include_router(voice.router, prefix="/ai", tags=["Voice"])
    
    # 只在主进程中输出日志（避免重载时重复输出）
    if _is_main_process:
        logger.info("✅ 所有创新功能路由已加载")
except ImportError as e:
    logger.warning(f"部分创新功能路由未加载: {e}")

# 健康检查端点
@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "service": "知弈 Agent",
        "version": "1.0.0"
    }


@app.get("/health/live")
async def liveness_check():
    return {"status": "UP", "service": "kinlin-ai-service", "check": "liveness"}


@app.get("/health/ready")
async def readiness_check():
    checks = {"dataDirectory": False, "packsRegistered": False, "workflowStore": False}
    try:
        _data_dir.mkdir(parents=True, exist_ok=True)
        probe = _data_dir / ".readiness-probe"
        probe.write_text("ready", encoding="utf-8")
        probe.unlink()
        checks["dataDirectory"] = True
        from app.api.agentos_core import runtime

        checks["packsRegistered"] = bool(runtime.workflow_registry.all())
        runtime.workflow_store.list_runs(page=1, page_size=1)
        checks["workflowStore"] = True
    except Exception as exc:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=503, content={"status": "DOWN", "checks": checks, "error": type(exc).__name__})
    return {"status": "UP", "checks": checks}


@app.get("/health/dependencies")
async def dependency_check():
    configured = bool(settings.DEEPSEEK_API_KEY or settings.DASHSCOPE_API_KEY or settings.QWEN_API_KEY or settings.KYLIN_AI_API_KEY)
    provider_state = {"status": "DISABLED", "affectsReadiness": False}
    if settings.PROVIDER_STATE_ENABLED:
        try:
            from app.llm.provider_conversation import configured_provider_conversation_manager

            manager = configured_provider_conversation_manager()
            provider_state["status"] = "UP" if manager and await manager.ping() else "DOWN"
        except Exception:
            provider_state["status"] = "DOWN"
    return {
        "status": "UP" if configured and provider_state["status"] != "DOWN" else "DEGRADED",
        "dependencies": {
            "modelProvider": {
                "status": "CONFIGURED" if configured else "UNCONFIGURED",
                "affectsReadiness": False,
            },
            "providerConversationState": provider_state,
        },
    }

# RAG路由
try:
    from app.api import rag
    app.include_router(rag.router, prefix="/rag", tags=["RAG"])
    if _is_main_process:
        logger.info("✅ RAG路由已加载")
except ImportError:
    logger.warning("RAG模块未实现，跳过注册")

@app.get("/")
async def root():
    return {"message": "知弈 AI Service", "version": "1.0.0"}

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )

