"""凭证：建单、保存、查询、提交。

契约见 docs/03-finance.md：

    POST   /api/vouchers              建单 = 首次保存，body 是整张单据
    GET    /api/vouchers              列表，支持状态 / 外部单号筛选
    GET    /api/vouchers/{id}         详情（表头 + 明细 + 错误 + 派生字段）
    PUT    /api/vouchers/{id}         再次保存（整张单据覆盖）
    POST   /api/vouchers/{id}/submit  提交入账，仅 checker

校验失败**不是 4xx**：保存成功就 200，结果在 body 的 {"ok": false, "errors": [...]} 里。
鉴权挂在路由级；POST 需要 created_by、submit 需要角色，这两个单独声明参数。
"""

from __future__ import annotations

import asyncio
import sqlite3
from sqlite3 import Connection
from typing import TypedDict, cast

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from .. import config, db, validation
from ..deps import CurrentUser, current_user, require_checker, require_maker
from ..errors import ApiError

router = APIRouter(tags=["vouchers"], dependencies=[Depends(current_user)])


# ---------------------------------------------------------------------------
# 请求 / 响应模型
# ---------------------------------------------------------------------------

class LineIn(BaseModel):
    """一行明细。金额单位是「分」，接口不接受浮点。"""

    account_code: str
    cost_center: str
    debit_cents: int = Field(ge=0)
    summary: str = ""


class VoucherIn(BaseModel):
    """整张单据。POST 建单和 PUT 保存收的是同一个形状。"""

    external_ref: str
    voucher_date: str               # YYYY-MM-DD
    summary: str
    dept_code: str
    attachment_count: int = Field(ge=0)
    lines: list[LineIn] = Field(default_factory=list)


class SaveResult(TypedDict):
    """保存结果。ok=False 时 errors 非空，HTTP 状态码仍然是 200。"""

    ok: bool
    errors: list[db.VoucherErrorRow]


class CreateResult(SaveResult):
    """建单结果，比保存多一个 id。"""

    id: int


def _to_input(payload: VoucherIn) -> db.VoucherInput:
    """Pydantic 模型 → 数据层要的 TypedDict 形状。"""
    return cast(db.VoucherInput, payload.model_dump())


# ---------------------------------------------------------------------------
# 接口
# ---------------------------------------------------------------------------

@router.post("/vouchers", status_code=status.HTTP_201_CREATED)
def create_voucher(
    payload: VoucherIn,
    user: CurrentUser = Depends(require_maker),
    conn: Connection = Depends(db.get_db),
) -> CreateResult:
    """建单 = 首次保存，返回新凭证的 id。只有制单角色能建单。

    单号重复由数据库的 UNIQUE 约束挡住，这里只负责把 IntegrityError 翻译成 409。
    """
    data = _to_input(payload)
    errors = validation.validate(conn, data)

    try:
        voucher_id = db.create_voucher(conn, data, user["username"], errors)
    except sqlite3.IntegrityError as exc:
        if "external_ref" in str(exc):
            raise ApiError(409, "DUPLICATE_DOC",
                           f"外部单号 {data['external_ref']} 已存在") from exc
        raise

    return {"id": voucher_id, "ok": not errors, "errors": errors}


@router.get("/vouchers")
def list_vouchers(
    status_filter: str | None = Query(default=None, alias="status"),
    external_ref: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    conn: Connection = Depends(db.get_db),
) -> db.VoucherPage:
    """凭证列表，支持按状态和外部单号筛选。过滤和分页都在数据层做。"""
    return db.list_vouchers(conn, status=status_filter, external_ref=external_ref, page=page)


@router.get("/vouchers/{voucher_id}")
def get_voucher(
    voucher_id: int,
    conn: Connection = Depends(db.get_db),
) -> db.VoucherDetail:
    """凭证详情：表头 + 明细 + 最近一次校验错误 + validated / total_cents。"""
    voucher = db.get_voucher(conn, voucher_id)
    if voucher is None:
        raise ApiError(404, "NOT_FOUND", f"凭证 {voucher_id} 不存在")
    return voucher


@router.put("/vouchers/{voucher_id}")
async def save_voucher(
    voucher_id: int,
    payload: VoucherIn,
    user: CurrentUser = Depends(require_maker),
    conn: Connection = Depends(db.get_db),
) -> SaveResult:
    """整张单据覆盖保存，返回校验结果。只有制单角色能改单。

    800ms 是刻意放大的服务端耗时，用来模拟查重 / 预算占用这类真实检查；
    前端必须处理"提交中"的等待态，不能假设点击后立刻有结果。
    """
    voucher = db.get_voucher(conn, voucher_id)
    if voucher is None:
        raise ApiError(404, "NOT_FOUND", f"凭证 {voucher_id} 不存在")
    if voucher["status"] != "draft":
        raise ApiError(409, "NOT_DRAFT", "已提交的凭证不能修改")

    await asyncio.sleep(config.VALIDATE_DELAY_MS / 1000)

    data = _to_input(payload)
    errors = validation.validate(conn, data)
    db.replace_voucher(conn, voucher_id, data, errors)

    return {"ok": not errors, "errors": errors}


class RejectIn(BaseModel):
    """驳回意见。为空时给一句默认话术。"""

    note: str = ""


@router.post("/vouchers/{voucher_id}/submit")
def submit_voucher(
    voucher_id: int,
    user: CurrentUser = Depends(require_maker),
    conn: Connection = Depends(db.get_db),
) -> db.VoucherDetail:
    """制单人提交审批：draft → pending。只有制单角色能送审。

    前置条件：存在、是草稿、最近一次保存校验通过。
    只是把单据送进复核队列，还没有入账——真正入账要 checker 通过。
    """
    voucher = db.get_voucher(conn, voucher_id)
    if voucher is None:
        raise ApiError(404, "NOT_FOUND", f"凭证 {voucher_id} 不存在")
    if voucher["status"] != "draft":
        raise ApiError(409, "NOT_DRAFT", "只有草稿可以提交审批")
    if not voucher["validated"]:
        raise ApiError(409, "NOT_VALIDATED", "凭证未通过校验，请先修正后再提交")

    db.mark_pending(conn, voucher_id, user["username"])

    submitted = db.get_voucher(conn, voucher_id)
    if submitted is None:
        raise ApiError(404, "NOT_FOUND", f"凭证 {voucher_id} 不存在")
    return submitted


@router.post("/vouchers/{voucher_id}/approve")
def approve_voucher(
    voucher_id: int,
    user: CurrentUser = Depends(require_checker),
    conn: Connection = Depends(db.get_db),
) -> db.VoucherDetail:
    """复核通过并入账：pending → submitted，分配凭证号。

    这是全流程唯一能把单据变成已入账的入口，且必须 checker 角色——
    agent 用 maker 账号，到这里就是 403。
    """
    voucher = db.get_voucher(conn, voucher_id)
    if voucher is None:
        raise ApiError(404, "NOT_FOUND", f"凭证 {voucher_id} 不存在")
    if voucher["status"] != "pending":
        raise ApiError(409, "NOT_PENDING", "只有待审批的凭证可以复核")

    for attempt in range(2):
        voucher_no = db.next_voucher_no(conn, voucher["voucher_date"])
        try:
            db.mark_approved(conn, voucher_id, voucher_no, user["username"])
            break
        except sqlite3.IntegrityError as exc:
            if attempt == 1:
                raise ApiError(409, "VOUCHER_NO_CONFLICT", "凭证号生成冲突，请重试") from exc

    approved = db.get_voucher(conn, voucher_id)
    if approved is None:
        raise ApiError(404, "NOT_FOUND", f"凭证 {voucher_id} 不存在")
    return approved


@router.post("/vouchers/{voucher_id}/reject")
def reject_voucher(
    voucher_id: int,
    payload: RejectIn,
    user: CurrentUser = Depends(require_checker),
    conn: Connection = Depends(db.get_db),
) -> db.VoucherDetail:
    """复核驳回：pending → draft，把意见写回单据。

    不删除凭证，也不清空明细——制单人改完可以重新提交。
    """
    voucher = db.get_voucher(conn, voucher_id)
    if voucher is None:
        raise ApiError(404, "NOT_FOUND", f"凭证 {voucher_id} 不存在")
    if voucher["status"] != "pending":
        raise ApiError(409, "NOT_PENDING", "只有待审批的凭证可以驳回")

    db.mark_rejected(conn, voucher_id, payload.note.strip() or "复核未通过")

    rejected = db.get_voucher(conn, voucher_id)
    if rejected is None:
        raise ApiError(404, "NOT_FOUND", f"凭证 {voucher_id} 不存在")
    return rejected
