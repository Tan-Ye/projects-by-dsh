"""登录相关接口。"""

from __future__ import annotations

from fastapi import APIRouter, Cookie, HTTPException, Response
from pydantic import BaseModel

import auth
import config

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(payload: LoginRequest, response: Response) -> dict[str, str]:
    display = auth.check_credentials(payload.username, payload.password)
    if display is None:
        raise HTTPException(status_code=401, detail="账号或口令不正确")

    response.set_cookie(
        auth.COOKIE_NAME,
        auth.issue_token(payload.username),
        httponly=True,
        samesite="lax",
        # 上了 HTTPS 再打开 COOKIE_SECURE；HTTP 下打开会直接登录不了
        secure=config.COOKIE_SECURE,
        max_age=auth.SESSION_TTL,
        path="/",
    )
    return {"username": payload.username, "display": display}


@router.post("/logout")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(wb_session: str | None = Cookie(default=None)) -> dict[str, object]:
    """当前登录用户。没登录返回 null，不是 401。

    "还没登录"是正常状态，不是错误——前端首次加载都会问一次，
    如果回 401，浏览器控制台会常驻一条红字，看起来像坏了。
    """
    username = auth.verify_token(wb_session)
    if username is None:
        return {"user": None}
    return {
        "user": {
            "username": username,
            "display": config.CONSOLE_USERS[username]["display"],
        }
    }


@router.get("/hint")
def hint() -> dict[str, list[str]]:
    """登录页展示的测试账号。内网自用，不藏着。"""
    return {"users": sorted(config.CONSOLE_USERS)}
