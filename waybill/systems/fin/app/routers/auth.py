"""登录：用户名密码换 token。

token 是后续所有请求的凭证，放在 `Authorization: Bearer <token>` 里。
签发和校验的配合见 deps.current_user。
"""

from __future__ import annotations

import secrets
import time
from sqlite3 import Connection
from typing import TypedDict

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .. import config
from ..db import create_session, get_db, get_user, verify_password
from ..errors import ApiError

router = APIRouter(tags=["auth"])


class LoginIn(BaseModel):
    """登录请求体。"""

    username: str
    password: str


class LoginResponse(TypedDict):
    """登录成功的返回。

    role 给前端决定要不要渲染"提交"按钮；真正的权限判断在 deps.require_checker，
    前端藏按钮只是体验，不是边界。
    """

    token: str
    expires_at: int
    username: str
    display_name: str
    role: str


@router.post("/login")
def login(payload: LoginIn, conn: Connection = Depends(get_db)) -> LoginResponse:
    """校验密码并签发 token。

    用户不存在、账号停用、密码错误三种情形合并成同一个错误，
    避免被用来枚举账号是否存在。
    """
    user = get_user(conn, payload.username)
    if user is None or not verify_password(payload.password, user["password_hash"]):
        raise ApiError(401, "INVALID_CREDENTIALS", "用户名或密码错误")

    token = secrets.token_urlsafe(24)
    # expires_at 存 unix 秒（sessions.expires_at 是 INTEGER），和 time.time() 直接比
    expires_at = int(time.time()) + config.TOKEN_TTL

    create_session(conn, token, user["username"], expires_at)
    # create_session 只执行不提交，事务边界归调用方：中途抛异常则整条会话不落库
    conn.commit()

    return {
        "token": token,
        "expires_at": expires_at,
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
    }
