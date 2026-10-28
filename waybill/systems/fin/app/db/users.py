"""用户与会话。"""

from __future__ import annotations

import sqlite3
from typing import cast

from .models import SessionRow, UserRow
from .timefmt import now_str


def get_user(conn: sqlite3.Connection, username: str) -> UserRow | None:
    """按用户名取一个**启用中**的用户；停用或不存在都返回 None。

    过滤 is_active 放在这里，调用方不用每次都记得加——停用账号在登录时
    会表现为"查无此人"，和密码错误合并成同一个错误，不泄漏账号状态。
    """
    row = conn.execute(
        "SELECT username, password_hash, display_name, role, is_active"
        " FROM users WHERE username = ? AND is_active = 1",
        (username,),
    ).fetchone()
    # 列名与 UserRow 逐一对齐，所以这里的 cast 是安全的
    return cast(UserRow, dict(row)) if row is not None else None


def create_session(
    conn: sqlite3.Connection, token: str, username: str, expires_at: int
) -> None:
    """登录成功后写入一条会话。

    created_at 按约定存定宽 TEXT（排序即时间序）；
    expires_at 是唯一例外，存 unix 秒（和 time.time() 直接比大小）。
    """
    conn.execute(
        "INSERT INTO sessions (token, username, created_at, expires_at) VALUES (?,?,?,?)",
        (token, username, now_str(), expires_at),
    )


def get_session(conn: sqlite3.Connection, token: str) -> SessionRow | None:
    """按 token 查会话，**不判过期**——过期与否由调用方决定怎么报错。

    SQL 里加 expires_at 条件会把"过期"和"不存在"合并成同一个 None，
    调用方就分不出该报 TOKEN_EXPIRED 还是 AUTH_REQUIRED。
    """
    row = conn.execute(
        "SELECT token, username, created_at, expires_at FROM sessions WHERE token = ?",
        (token,),
    ).fetchone()
    # 列名与 SessionRow 逐一对齐
    return cast(SessionRow, dict(row)) if row is not None else None
