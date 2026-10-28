"""认证依赖。

解析 `Authorization: Bearer <token>`，校验会话与有效期，返回当前用户。

角色只有两个：
  - maker   ：建草稿、编辑、保存校验（agent 用这个）
  - checker ：额外拥有提交入账权限

「提交必须人点」靠这里强制，不靠前端隐藏按钮。
"""

from __future__ import annotations

import time
from sqlite3 import Connection
from typing import TypedDict

from fastapi import Depends, Header

from .db import get_db, get_session, get_user
from .errors import ApiError


class CurrentUser(TypedDict):
    """当前登录人，路由里唯一可信的身份来源。"""

    username: str
    role: str
    display_name: str


async def current_user(
    authorization: str | None = Header(default=None),
    conn: Connection = Depends(get_db),
) -> CurrentUser:
    """从 Authorization 头解析 token，返回当前用户。

    三种失败分开报：
      - 没头 / 格式不对 / token 查不到 → AUTH_REQUIRED
      - token 过期                      → TOKEN_EXPIRED
      - 账号停用或已删                  → AUTH_REQUIRED（视作未登录）

    "过期"和"不存在"必须分开：前端只有看到 TOKEN_EXPIRED 才知道该重新登录，
    而不是以为自己凭证错了。
    """
    if authorization is None or not authorization.lower().startswith("bearer "):
        raise ApiError(401, "AUTH_REQUIRED", "请先登录")

    # "Bearer " 正好 7 个字符；scheme 大小写不敏感，上面用 lower() 判断
    token = authorization[7:].strip()
    session = get_session(conn, token)
    if session is None:
        raise ApiError(401, "AUTH_REQUIRED", "登录已失效，请重新登录")

    # expires_at 存 unix 秒（INTEGER），和 time.time() 直接比；两边都取 int 避免 float 边界
    if int(session["expires_at"]) <= int(time.time()):
        raise ApiError(401, "TOKEN_EXPIRED", "登录已过期，请重新登录")

    # get_user 自带 is_active = 1，账号一停用这里就查不到
    user = get_user(conn, session["username"])
    if user is None:
        raise ApiError(401, "AUTH_REQUIRED", "账号不存在或已停用")

    return {
        "username": user["username"],
        "role": user["role"],
        "display_name": user["display_name"],
    }


async def require_checker(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    """复核动作的权限闸门：只有 checker 能过。

    通过/驳回都在这一侧——「终审必须人点」靠接口强制，不靠前端藏按钮。
    """
    if user["role"] != "checker":
        raise ApiError(403, "NOT_PERMITTED", "只有复核角色可以执行该操作")
    return user


async def require_maker(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    """制单动作的权限闸门：只有 maker 能过。

    建单、保存、提交审批都归制单人。复核人只看不改——
    如果复核的人能顺手改单，制单/复核的分权就没有意义了。
    """
    if user["role"] != "maker":
        raise ApiError(403, "NOT_PERMITTED", "只有制单角色可以建单和保存")
    return user
