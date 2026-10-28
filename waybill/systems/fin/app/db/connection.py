"""连接与初始化。

DDL 在 `app/schema.sql` —— SQL 归 SQL，Python 归 Python，
DBeaver / sqlite3 CLI 也能直接打开它。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator

from .. import config

# 基于本文件定位，不能用 cwd：换个目录启动就找不到了
SCHEMA_FILE = Path(__file__).resolve().parent.parent / "schema.sql"


def connect() -> sqlite3.Connection:
    """打开一个连接，并做好两件每次都必须做的事。"""
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    # 不开 row_factory 的话，fetchone() 返回的是普通元组，只能按下标取
    conn.row_factory = sqlite3.Row
    # SQLite 默认不校验外键，每条连接都要单独打开
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db() -> Iterator[sqlite3.Connection]:
    """FastAPI 依赖：一个请求一个连接，请求结束自动关闭。"""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """启动时调用：建表 + 灌种子。

    必须幂等——每次启动都会跑，重复执行不能报错、不能重复插数据。
    """
    # 延迟导入：seed 依赖 passwords，而连接层不应该在 import 时就建立这条依赖
    from .seed import seed

    conn = connect()
    try:
        conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
        seed(conn)
        conn.commit()
    finally:
        conn.close()
