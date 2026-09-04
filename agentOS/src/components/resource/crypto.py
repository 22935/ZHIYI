"""At-rest protection for resource signing secrets."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class ResourceSecretBox:
    """Encrypt resource secrets with a configured Fernet master key."""

    def __init__(self, key: str | bytes | None = None) -> None:
        material = key or Fernet.generate_key()
        if isinstance(material, str):
            material = material.encode("ascii")
        try:
            self._fernet = Fernet(material)
        except (TypeError, ValueError) as error:
            raise ValueError("resource credential key must be a valid Fernet key") from error

    def encrypt(self, secret: str) -> str:
        return self._fernet.encrypt(secret.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError, ValueError) as error:
            raise ValueError("resource credential ciphertext is invalid") from error
