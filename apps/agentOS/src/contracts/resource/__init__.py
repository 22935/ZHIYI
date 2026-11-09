"""跨组件共享的资源合同与请求签名合同。"""

from .resource import *
from .resource import __all__ as _resource_all
from .resource_signing import build_resource_signature, canonical_resource_request

__all__ = [
    *_resource_all,
    "build_resource_signature",
    "canonical_resource_request",
]
