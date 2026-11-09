"""凭据密文保护端口，由应用层注入具体密钥管理实现。"""

from typing import Protocol


class SecretBox(Protocol):
    """把敏感凭据转换为可持久化密文并在受控边界解密。"""

    def encrypt(self, secret: str) -> str: ...

    def decrypt(self, ciphertext: str) -> str: ...
