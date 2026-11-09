"""资源认证凭据的领域值对象；不暴露存储后端细节。"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ResourceCredentialRecord:
    """保存凭据索引、摘要及加密密文的内部记录。"""

    resource_id: str
    credential_id: str
    owner_scope: str
    secret_digest: str
    encrypted_secret: str
    created_at: datetime
