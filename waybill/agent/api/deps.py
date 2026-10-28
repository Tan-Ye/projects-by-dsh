"""接口共用的依赖。"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import store


def get_conn() -> Iterator[sqlite3.Connection]:
    """每个请求一个连接，请求结束就关。

    SQLite 连接不贵，池化反而要处理"谁负责关"的问题。
    """
    conn = store.connect()
    try:
        yield conn
    finally:
        conn.close()
