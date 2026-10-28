"""控制台登录：固定账号 + 签名 cookie。

为什么不引第三方库：
    需求只有"几个固定账号 + 别让人随便进"。
    签名 cookie 用 hmac 就够，多一个依赖不划算。

上线前要改的两处：账号从环境变量注入、cookie 加 secure=True。
"""

from __future__ import annotations

import hashlib
import hmac
import time

from fastapi import Cookie, HTTPException

import config

COOKIE_NAME = "wb_session"
SESSION_TTL = 8 * 3600


def _sign(payload: str) -> str:
    return hmac.new(
        config.CONSOLE_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def issue_token(username: str) -> str:
    """生成 token：user.expiry.signature，三段用点分隔。"""
    expiry = int(time.time()) + SESSION_TTL
    payload = f"{username}.{expiry}"
    return f"{payload}.{_sign(payload)}"


def verify_token(token: str | None) -> str | None:
    """校验 token。返回用户名；无效或过期返回 None。"""
    if not token:
        return None
    try:
        username, expiry_text, signature = token.rsplit(".", 2)
        expiry = int(expiry_text)
    except ValueError:
        return None

    if not hmac.compare_digest(signature, _sign(f"{username}.{expiry}")):
        return None
    if expiry < time.time():
        return None
    return username


def check_credentials(username: str, password: str) -> str | None:
    """校验账号口令，返回显示名；不通过返回 None。"""
    user = config.CONSOLE_USERS.get(username)
    if user is None:
        return None
    if not hmac.compare_digest(user["password"], password):
        return None
    return user["display"]


def current_user(wb_session: str | None = Cookie(default=None)) -> str:
    """FastAPI 依赖：从 cookie 取当前用户，取不到就 401。"""
    username = verify_token(wb_session)
    if username is None:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return username
