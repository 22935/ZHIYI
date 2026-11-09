"""ResourcePlane 各 SQLite 存储共享的耐久性与锁竞争设置。

所有 SQLite 实例通过此函数初始化，保证 WAL、忙等待、外键约束等关键语义
一致，避免不同资源表因连接参数不一致而表现出不同的并发行为。
"""

from __future__ import annotations

import sqlite3


def configure_sqlite_connection(
    connection: sqlite3.Connection, *, busy_timeout_ms: int = 30_000
) -> sqlite3.Connection:
    """向每个资源数据库连接应用相同的本地安全配置。

    TODO(architecture-evolution): SQLite 仅适合本地/嵌入式模式；生产级
    ResourcePlane 应迁移到 PostgreSQL，并由 Redis 协调租约。
    """
    connection.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA temp_store = MEMORY")
    return connection


__all__ = ["configure_sqlite_connection"]
