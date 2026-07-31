"""AgentOS Core 的适配器 __init__ 模块，连接模型、检索和联邦增强等外部能力。"""



from agentos.adapters.federated_adapter import FederatedAdapter
from agentos.adapters.model_adapter import (
    AIService,
    ModelAdapter,
    ModelService,
    ModelServiceFactory,
    StructuredGenerationError,
    StructuredGenerationResult,
    StructuredGenerationRuntime,
    clear_model_service_factory,
    register_model_service_factory,
)

__all__ = [
    "AIService",
    "FederatedAdapter",
    "ModelAdapter",
    "ModelService",
    "ModelServiceFactory",
    "StructuredGenerationError",
    "StructuredGenerationResult",
    "StructuredGenerationRuntime",
    "clear_model_service_factory",
    "register_model_service_factory",
]
