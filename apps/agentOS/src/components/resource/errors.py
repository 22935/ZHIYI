"""由 ResourcePlane 观测写入路径显式抛出的领域错误。

将锁竞争、乐观并发冲突和异常时间戳区分开来，使调用方能够按可恢复性
选择重试、丢弃或告警，而不是把所有异常笼统视为持久化失败。
"""

from __future__ import annotations


class ResourceObservationPersistenceError(RuntimeError):
    """资源观测无法可靠地持久化。"""


class ResourceDatabaseLockedError(ResourceObservationPersistenceError):
    """SQLite 锁竞争超过限定重试窗口。"""


class ResourceVersionConflictError(ResourceObservationPersistenceError):
    """观测在乐观 CAS 重试后仍无法合并。"""


class ResourceObservationTimeInvalidError(ValueError):
    """远程观测携带不可信的未来时间戳。"""


class ResourceConfigMismatchError(ValueError):
    """重复资源登记携带了不同的静态配置。"""


__all__ = [
    "ResourceConfigMismatchError",
    "ResourceDatabaseLockedError",
    "ResourceObservationPersistenceError",
    "ResourceObservationTimeInvalidError",
    "ResourceVersionConflictError",
]
