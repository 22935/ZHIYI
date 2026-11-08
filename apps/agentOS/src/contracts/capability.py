"""外部模型、智能体、技能和工具接入的稳定能力合同。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CapabilityKind(str, Enum):
    """标识统一兼容层可登记的四类外部能力。"""

    MODEL = "model"
    AGENT = "agent"
    SKILL = "skill"
    TOOL = "tool"


class ModelCapabilitySource(str, Enum):
    """模型物理能力事实的来源；未知值不得被产品默认值替代。"""

    PROVIDER_REPORTED = "provider_reported"
    ADAPTER_DECLARED = "adapter_declared"
    RUNTIME_OBSERVED = "runtime_observed"
    UNKNOWN = "unknown"


class ModelOutputPolicy(str, Enum):
    """结构化生成的输出边界决策来源。"""

    API_CONTROLLED = "api_controlled"
    PROVIDER_REQUIRED = "provider_required"
    EXPLICIT = "explicit"
    CATALOG_DEFAULT = "catalog_default"


class ModelProvider(str, Enum):
    """列出首期需兼容的云端、本地与 OpenAI 兼容模型来源。"""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    AZURE_OPENAI = "azure_openai"
    AWS_BEDROCK = "aws_bedrock"
    ALIBABA_QWEN = "alibaba_qwen"
    BAIDU_QIANFAN = "baidu_qianfan"
    ZHIPU = "zhipu"
    DEEPSEEK = "deepseek"
    OLLAMA = "ollama"
    VLLM = "vllm"
    OPENAI_COMPATIBLE = "openai_compatible"
    CUSTOM = "custom"


class AgentArchitecture(str, Enum):
    """标识可映射到 AgentOS 的常见单体和多智能体编排形态。"""

    SINGLE = "single"
    REACT = "react"
    PLAN_EXECUTE = "plan_execute"
    SUPERVISOR = "supervisor"
    HIERARCHICAL = "hierarchical"
    SWARM = "swarm"
    GRAPH = "graph"
    EVENT_DRIVEN = "event_driven"
    PIPELINE = "pipeline"
    DEBATE = "debate"
    REFLECTION = "reflection"
    MULTI_AGENT = "multi_agent"


class AgentFramework(str, Enum):
    """列出原生及主流开源/开放 Agent 框架适配标识。"""

    NATIVE = "native"
    LANGCHAIN = "langchain"
    LANGGRAPH = "langgraph"
    AUTOGEN = "autogen"
    CREWAI = "crewai"
    LLAMAINDEX = "llamaindex"
    SEMANTIC_KERNEL = "semantic_kernel"
    HAYSTACK = "haystack"
    OPENAI_AGENTS = "openai_agents"
    GOOGLE_ADK = "google_adk"
    CUSTOM = "custom"


class ToolProtocol(str, Enum):
    """标识工具和技能应遵循的互操作协议。"""

    NATIVE = "native"
    MCP = "mcp"
    OPENAPI = "openapi"
    FUNCTION_CALLING = "function_calling"
    HTTP = "http"
    PYTHON = "python"
    CUSTOM = "custom"


class CapabilityManifest(BaseModel):
    """描述一个可发现能力的身份、协议、版本与声明性边界。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    capability_id: str = Field(alias="capabilityId", min_length=1)
    kind: CapabilityKind
    display_name: str = Field(alias="displayName", min_length=1)
    version: str = "v1"
    provider: str = ""
    architecture: AgentArchitecture | None = None
    framework: AgentFramework | None = None
    protocol: ToolProtocol | None = None
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelFeatureSet(BaseModel):
    """供应商无关的模型功能声明；缺失表示未声明而不是不支持。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    json_schema: bool | None = Field(default=None, alias="jsonSchema")
    streaming: bool | None = None
    tools: bool | None = None
    thinking: bool | None = None
    prompt_caching: bool | None = Field(default=None, alias="promptCaching")


class ModelCapabilityEnvelope(BaseModel):
    """一个精确 provider/model 路由在某一时刻的能力快照。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    version: str | None = None
    revision: str | None = None
    source: ModelCapabilitySource = ModelCapabilitySource.UNKNOWN
    context_window_tokens: int | None = Field(default=None, alias="contextWindowTokens", ge=1)
    max_output_tokens: int | None = Field(default=None, alias="maxOutputTokens", ge=1)
    max_tokens_field: str | None = Field(default=None, alias="maxTokensField")
    max_tokens_required: bool = Field(default=False, alias="maxTokensRequired")
    features: ModelFeatureSet = Field(default_factory=ModelFeatureSet)
    observed_at: datetime | None = Field(default=None, alias="observedAt")

    @classmethod
    def unknown(
        cls,
        *,
        provider: str,
        model: str,
        version: str | None = None,
    ) -> "ModelCapabilityEnvelope":
        return cls(provider=provider, model=model, version=version)


class ModelInvocationRequest(BaseModel):
    """定义供应商无关的模型调用输入，不携带任何 SDK 对象。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    request_id: str = Field(alias="requestId", min_length=1)
    model: str = Field(min_length=1)
    messages: list[dict[str, Any]] = Field(default_factory=list)
    response_schema: dict[str, Any] | None = Field(default=None, alias="responseSchema")
    # A continuation retains the earlier transport contract in its original
    # prefix; the active response contract is appended after the new messages.
    prefix_response_schema: dict[str, Any] | None = Field(default=None, alias="prefixResponseSchema")
    # Internal wire-layout instruction; never forwarded as a provider option.
    schema_message_index: int | None = Field(default=None, alias="schemaMessageIndex", ge=0, strict=True)
    options: dict[str, Any] = Field(default_factory=dict)
    # 模型请求与 ACG 节点提交边界的关联标识。它不是 prompt、模型正文或检查点状态；
    # 支持幂等键的应用层传输可将它安全映射为 HTTP Header 或供应商请求标识。
    commit_id: str | None = Field(default=None, alias="commitId")


class ModelInvocationResponse(BaseModel):
    """定义模型调用的规范化响应与可审计元数据投影。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    request_id: str = Field(alias="requestId", min_length=1)
    content: dict[str, Any] = Field(default_factory=dict)
    provider: str
    model: str
    usage: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelStreamEvent(BaseModel):
    """模型流式调用的会话内事件，不属于执行 State 或审计持久化合同。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    request_id: str = Field(alias="requestId", min_length=1)
    event_type: Literal["activity", "delta", "tool_call", "completed"] = Field(alias="eventType")
    delta: str = ""
    provider: str
    model: str
    # 工具参数可能由供应商分片返回，只允许作为当前流会话的瞬时投影；调用方不得
    # 把它们写入 Workflow State、checkpoint 或 Trace。
    tool_call_id: str | None = Field(default=None, alias="toolCallId")
    tool_name: str | None = Field(default=None, alias="toolName")
    tool_arguments: str = Field(default="", alias="toolArguments")
    metadata: dict[str, Any] = Field(default_factory=dict)


class CapabilityInvocation(BaseModel):
    """定义智能体、技能或工具的统一调用信封。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    invocation_id: str = Field(alias="invocationId", min_length=1)
    capability_id: str = Field(alias="capabilityId", min_length=1)
    input: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)


class CapabilityInvocationResult(BaseModel):
    """定义外部能力调用的规范化结果，不规定具体执行语义。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    invocation_id: str = Field(alias="invocationId", min_length=1)
    success: bool
    output: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "AgentArchitecture", "AgentFramework", "CapabilityInvocation",
    "CapabilityInvocationResult", "CapabilityKind", "CapabilityManifest",
    "ModelCapabilityEnvelope", "ModelCapabilitySource", "ModelFeatureSet",
    "ModelInvocationRequest", "ModelInvocationResponse", "ModelProvider", "ModelStreamEvent",
    "ModelOutputPolicy",
    "ToolProtocol",
]
