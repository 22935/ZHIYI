"""资源生命周期事实；元数据只保存标识、原因分类，不保存业务正文和密钥。"""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class ResourceAuditEvent:
    kind: str
    resource_id: str
    occurred_at: datetime
    metadata: dict[str, str] = field(default_factory=dict)
