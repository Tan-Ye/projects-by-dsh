"""时间格式。

项目约定：定宽字符串 `YYYY-MM-DD HH:MM:SS`，字典序即时间序。
唯一的例外是 `sessions.expires_at`，它存 unix 秒（见 schema.sql）。
"""

from __future__ import annotations

from datetime import datetime


def now_str() -> str:
    """当前时间，按项目的定宽格式。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
