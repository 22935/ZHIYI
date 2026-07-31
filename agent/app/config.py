"""
配置管理
所有配置统一从主目录的.env文件读取
"""
try:
    from pydantic import field_validator
    from pydantic_settings import BaseSettings
except ModuleNotFoundError:
    from pydantic.v1 import BaseSettings, validator

    def field_validator(*fields, mode=None, **kwargs):
        def decorator(func):
            if isinstance(func, classmethod):
                func = func.__func__
            return validator(*fields, pre=mode == "before", allow_reuse=True)(func)

        return decorator
from typing import List
from pathlib import Path
import os
from dotenv import load_dotenv


def _load_secret_file(variable: str, *, allow_empty: bool = False) -> str | None:
    file_path = os.getenv(f"{variable}_FILE", "").strip()
    if not file_path:
        return None
    path = Path(file_path)
    if not path.is_file():
        raise RuntimeError(f"secret file for {variable} is missing: {path}")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        if allow_empty:
            return None
        raise RuntimeError(f"secret file for {variable} is empty: {path}")
    return value


_secret_file_values = {
    variable: value
    for variable in (
        "AI_INTERNAL_TOKEN",
        "DEEPSEEK_API_KEY",
        "DASHSCOPE_API_KEY",
        "QWEN_API_KEY",
        "KYLIN_AI_API_KEY",
        "TAVILY_API_KEY",
        "REDIS_PASSWORD",
    )
    if (value := _load_secret_file(variable, allow_empty=variable != "AI_INTERNAL_TOKEN")) is not None
}

# 显式加载.env文件（优先检查当前目录，然后检查主目录）
_config_path = Path(__file__).resolve()

# 优先检查当前目录的.env文件
_current_dir_env = Path(".env")
_env_file_path = _current_dir_env

if _current_dir_env.exists():
    # 加载当前目录的.env文件
    result = load_dotenv(dotenv_path=str(_current_dir_env), override=True)
else:
    # 回退到主目录的.env文件
    _project_root = _config_path.parent.parent.parent  # 从 agent/app/ 到主目录
    _env_file_path = _project_root / ".env"
    if _env_file_path.exists():
        result = load_dotenv(dotenv_path=str(_env_file_path), override=True)
    else:
        _env_file_path = None

class Settings(BaseSettings):
    # 应用配置
    APP_NAME: str = "知弈 AI Service"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"
    AI_INTERNAL_TOKEN: str = ""
    SSE_HEARTBEAT_INTERVAL: float = 15.0
    SSE_TEST_MODE: bool = False
    PROVIDER_STATE_ENABLED: bool = False
    PROVIDER_STATE_REDIS_URL: str = "redis://redis:6379/0"
    PROVIDER_STATE_TTL_SECONDS: int = 3600
    REDIS_PASSWORD: str = ""
    TOOL_RUNTIME_ENABLED: bool = True
    TAVILY_API_KEY: str = ""
    TOOL_MAX_TURNS: int = 6
    TOOL_MAX_CALLS: int = 8
    TOOL_TIMEOUT_SECONDS: float = 15.0
    TOOL_SEARCH_MAX_RESULTS: int = 5
    TOOL_EXTRACT_MAX_URLS: int = 3
    TOOL_CODEBASE_ROOT: str = ""

    @field_validator("DEBUG", mode="before")
    @classmethod
    def normalize_debug_flag(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production", "false", "0", "off", "no"}:
                return False
            if normalized in {"debug", "dev", "development", "true", "1", "on", "yes"}:
                return True
        return value
    
    # 麒麟AI SDK配置（兼容旧配置）
    KYLIN_AI_API_KEY: str = ""  # 默认空字符串，可通过环境变量或.env文件设置
    KYLIN_AI_ENDPOINT: str = "https://api.kylin.ai"
    KYLIN_AI_TIMEOUT: int = 240
    
    # 通义千问配置（推荐使用）
    # 所有配置都从.env文件读取，系统全局只保留这一个配置来源
    # 支持两种环境变量名称：DASHSCOPE_API_KEY（官方推荐）和 QWEN_API_KEY（兼容旧配置）
    DASHSCOPE_API_KEY: str = ""  # 通义千问API密钥（官方环境变量名），从 https://dashscope.aliyuncs.com/ 获取，必须在.env文件中配置
    QWEN_API_KEY: str = ""  # 通义千问API密钥（兼容旧配置），如果DASHSCOPE_API_KEY未设置则使用此值，必须在.env文件中配置
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"  # 通义千问API基础URL，可在.env文件中覆盖
    QWEN_MODEL_FAST: str = "qwen-turbo"  # 快速模型，可在.env文件中配置
    QWEN_MODEL_BALANCED: str = "qwen-plus"  # 平衡模型（推荐），可在.env文件中配置
    QWEN_MODEL_ADVANCED: str = "qwen-max"  # 高级模型，可在.env文件中配置
    QWEN_MODEL_LATEST: str = "qwen3-max"  # 最新模型（推荐用于高质量场景），可在.env文件中配置
    QWEN_ENABLED: bool = True  # 是否启用通义千问（如果设置了API密钥则自动启用），可在.env文件中配置

    # DeepSeek 配置（文本生成主引擎，速度快）
    DEEPSEEK_API_KEY: str = ""  # DeepSeek API密钥，从 https://platform.deepseek.com/ 获取
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"  # DeepSeek API基础URL
    DEEPSEEK_MODEL: str = "deepseek-v4-flash"  # DeepSeek模型名称
    DEEPSEEK_ENABLED: bool = True  # 是否启用DeepSeek

    # 文本生成引擎选择: "deepseek" | "qwen" | "auto"
    TEXT_ENGINE: str = "auto"  # auto=优先DeepSeek，未配置key则回退Qwen

    # 模型配置
    TEXT_MODEL_NAME: str = "default"
    ASR_MODEL_NAME: str = "default"
    TTS_MODEL_NAME: str = "default"
    
    # 图像生成配置（通义万相wanx）
    IMAGE_GENERATION_MODEL: str = "wan2.6-t2i"  # 图像生成模型，可在.env文件中配置
    # 支持的模型：
    # - wan2.6-t2i: 通义万相2.6文本到图像（推荐，最新模型）⭐
    # - wanx-v1: 通义万相v1（旧版API，兼容）
    # - wanx-v1.5: 通义万相v1.5（旧版API，兼容）
    
    # 文档处理配置
    DOCUMENT_PROCESSOR_METHOD: str = "auto"  # 文档处理方法：auto/mineru/easydoc/pdfplumber/pypdf2
    DOCUMENT_PROCESSOR_USE_ENHANCED: bool = True  # 是否使用增强文档处理工具
    
    # RAG工具配置
    RAG_TOOL_PROVIDER: str = "auto"  # RAG工具提供商：auto/ragflow/qanything/fastgpt/builtin
    FASTGPT_API_URL: str = ""  # FastGPT API地址（可选）
    FASTGPT_API_KEY: str = ""  # FastGPT API密钥（可选）
    RAGFLOW_API_URL: str = ""  # RagFlow API地址（可选）
    RAGFLOW_API_KEY: str = ""  # RagFlow API密钥（可选）
    QANYTHING_API_URL: str = ""  # QAnything API地址（可选）
    QANYTHING_API_KEY: str = ""  # QAnything API密钥（可选）
    
    # CORS配置
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8080"
    ]
    
    class Config:
        # .env文件路径：主目录下（与agent同级）
        # 从 agent/app/config.py 访问主目录的 .env
        # __file__ = agent/app/config.py
        # parent.parent.parent = 主目录（Kinlin_AI）
        # 注意：env_file可以是相对路径或绝对路径
        # 由于已经通过load_dotenv显式加载，这里也可以使用环境变量
        env_file = str(_env_file_path) if (_env_file_path and _env_file_path.exists()) else None
        case_sensitive = False
        # 允许忽略.env文件中的额外字段（这些字段可能是给后端Java服务等其他服务使用的）
        extra = "ignore"
        # 从环境变量读取（load_dotenv已经加载了.env文件到环境变量）
        env_file_encoding = 'utf-8'

# 初始化配置
try:
    settings = Settings(**_secret_file_values)
    from app.utils.logger import configure_logging
    import logging
    configure_logging(
        json_format=settings.ENVIRONMENT.strip().lower() in {"prod", "production"},
        level=logging.INFO,
    )
    
    # 验证关键配置项是否加载（在Settings初始化后检查）
    if not settings.DEEPSEEK_API_KEY and not settings.DASHSCOPE_API_KEY and not settings.QWEN_API_KEY:
        import logging
        _warn_logger = logging.getLogger(__name__)
        _warn_logger.warning("未配置可用的模型 API Key")
        if _env_file_path:
            _warn_logger.warning(f"   配置文件路径: {_env_file_path}")
        _warn_logger.warning(f"   请在.env文件中添加以下配置项之一:")
        _warn_logger.warning("   请通过对应 Secret 文件配置模型 API Key")
        _warn_logger.warning(f"   获取API密钥: https://dashscope.aliyuncs.com/")
    else:
        import logging
        _info_logger = logging.getLogger(__name__)
        if settings.DEEPSEEK_API_KEY:
            _info_logger.info("DeepSeek API key loaded from config.")
        elif settings.DASHSCOPE_API_KEY:
            _info_logger.info("DashScope API key loaded from config.")
        else:
            _info_logger.info("Qwen API key loaded from config.")
        
except Exception as e:
    import logging
    _init_logger = logging.getLogger(__name__)
    _init_logger.error(f"配置加载失败: {e}")
    raise

# 清理配置值（去除注释和多余空格）
def _clean_config_value(value: str) -> str:
    """清理配置值，去除行内注释和多余空格"""
    if not value:
        return value
    # 去除首尾空格
    value = value.strip()
    if '#' in value:
        value = value.split('#')[0].strip()
    return value

# 清理模型配置值（如果包含注释）
# 注意：直接修改settings对象的属性值
if hasattr(settings, 'QWEN_MODEL_BALANCED'):
    original_value = str(settings.QWEN_MODEL_BALANCED)
    cleaned_value = _clean_config_value(original_value)
    if cleaned_value != original_value:
        object.__setattr__(settings, 'QWEN_MODEL_BALANCED', cleaned_value)

if hasattr(settings, 'QWEN_MODEL_FAST'):
    original_value = str(settings.QWEN_MODEL_FAST)
    cleaned_value = _clean_config_value(original_value)
    if cleaned_value != original_value:
        object.__setattr__(settings, 'QWEN_MODEL_FAST', cleaned_value)

if hasattr(settings, 'QWEN_MODEL_ADVANCED'):
    original_value = str(settings.QWEN_MODEL_ADVANCED)
    cleaned_value = _clean_config_value(original_value)
    if cleaned_value != original_value:
        object.__setattr__(settings, 'QWEN_MODEL_ADVANCED', cleaned_value)

if hasattr(settings, 'QWEN_MODEL_LATEST'):
    original_value = str(settings.QWEN_MODEL_LATEST)
    cleaned_value = _clean_config_value(original_value)
    if cleaned_value != original_value:
        object.__setattr__(settings, 'QWEN_MODEL_LATEST', cleaned_value)

# 配置加载后的验证和日志
import logging

# 使用统一的日志工具（如果可用）
try:
    from app.utils.logger import get_logger
    _logger = get_logger("config")
except ImportError:
    # 如果logger工具不可用，使用基本配置
    _logger = logging.getLogger(__name__)
    _logger.setLevel(logging.INFO)

# 获取配置文件路径（使用正确的路径）
_env_file_path_correct = Path(".env")

# 配置信息不再详细输出，只在需要时输出警告

# 从环境变量和settings双重检查（确保配置正确加载）
_dashscope_key_env = os.getenv('DASHSCOPE_API_KEY', '') or ''
_qwen_key_env = os.getenv('QWEN_API_KEY', '') or ''
_deepseek_key_env = os.getenv('DEEPSEEK_API_KEY', '') or ''
_dashscope_key_raw = settings.DASHSCOPE_API_KEY or _dashscope_key_env or ''
_qwen_key_raw = settings.QWEN_API_KEY or _qwen_key_env or ''
_deepseek_key_raw = settings.DEEPSEEK_API_KEY or _deepseek_key_env or ''
_dashscope_key = _clean_config_value(_dashscope_key_raw)
_qwen_key = _clean_config_value(_qwen_key_raw)
_deepseek_key = _clean_config_value(_deepseek_key_raw)
_api_key_configured = bool(_deepseek_key or _dashscope_key or _qwen_key)

# 更新settings中的值（如果从环境变量读取到了，或需要清理）
if _dashscope_key and _dashscope_key != settings.DASHSCOPE_API_KEY:
    object.__setattr__(settings, 'DASHSCOPE_API_KEY', _dashscope_key)
if _qwen_key and _qwen_key != settings.QWEN_API_KEY:
    object.__setattr__(settings, 'QWEN_API_KEY', _qwen_key)
if _deepseek_key and _deepseek_key != settings.DEEPSEEK_API_KEY:
    object.__setattr__(settings, 'DEEPSEEK_API_KEY', _deepseek_key)

if _api_key_configured:
    # 配置正常时不输出详细信息，只在未配置时输出警告
    pass
else:
    _logger.warning("通义千问API密钥未配置")
    _logger.warning(f"   配置文件路径: {_env_file_path_correct}")
    _logger.warning("   请通过对应 Secret 文件配置模型 API Key")
    _logger.warning(f"   获取API密钥: https://dashscope.aliyuncs.com/")
    _logger.warning(f"   提示: 运行 'python debug_config.py' 可以诊断配置问题")

