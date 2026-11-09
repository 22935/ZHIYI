"""兼容旧导入路径；签名规范的实现位于 ``contracts.resource``。"""

from .resource.resource_signing import build_resource_signature, canonical_resource_request

__all__ = ["build_resource_signature", "canonical_resource_request"]
