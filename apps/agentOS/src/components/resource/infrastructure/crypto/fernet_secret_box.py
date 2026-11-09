"""资源签名密钥的静态存储保护。

数据库仅保存 Fernet 密文与摘要；明文只在签名校验边界短暂解密，避免
持久化层或日志意外暴露远程资源的共享密钥。
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from ...ports.secret_box import SecretBox


class ResourceSecretBox(SecretBox):
    """使用配置的 Fernet 主密钥加密、解密资源密钥。"""

    def __init__(self, key: str | bytes | None = None) -> None:
        material = key or Fernet.generate_key()
        if isinstance(material, str):
            material = material.encode("ascii")
        try:
            self._fernet = Fernet(material)
        except (TypeError, ValueError) as error:
            raise ValueError("resource credential key must be a valid Fernet key") from error

    def encrypt(self, secret: str) -> str:
        """将 UTF-8 明文转为可安全写入文本字段的 ASCII 密文。"""
        return self._fernet.encrypt(secret.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        """解密并统一转换异常，避免向调用方泄露底层令牌细节。"""
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError, ValueError) as error:
            raise ValueError("resource credential ciphertext is invalid") from error


# TODO(key-management): 生产环境应从受管 KMS/HSM 注入并轮换主密钥，不能依赖进程内临时生成的密钥。
