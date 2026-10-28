"""批次接口：启动、列表、详情。

启动是异步的：接口只负责建批次 + 起后台任务，立刻返回 batch_id。
执行过程和凭据都不经过数据库——凭据只在内存的闭包里活几秒。
"""

from __future__ import annotations

import asyncio
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import auth
import config
import store
from api.deps import get_conn
from flows.batch import run_batch

router = APIRouter(prefix="/api/batches", tags=["batches"])

# 同一时间只允许一个批次：两个浏览器、两个会话同时跑，结果会互相打架
_running: set[int] = set()


class BatchStart(BaseModel):
    username: str
    password: str
    status_filter: str = ""
    max_scan: int = 5


class BatchItem(BaseModel):
    doc_no: str
    outcome: str
    task_id: int | None
    note: str
    created_at: str


async def _execute(batch_id: int, payload: BatchStart) -> None:
    try:
        await run_batch(
            batch_id=batch_id,
            username=payload.username,
            password=payload.password,
            status_filter=payload.status_filter,
            max_scan=payload.max_scan,
        )
    finally:
        # 凭据随闭包一起消失，这里不保留任何引用
        _running.discard(batch_id)


@router.post("")
async def start(
    payload: BatchStart,
    conn: sqlite3.Connection = Depends(get_conn),
    username: str = Depends(auth.current_user),
) -> dict[str, object]:
    if _running:
        raise HTTPException(status_code=409, detail="已有批次在运行，等它跑完再启动")

    if not payload.username.strip() or not payload.password:
        raise HTTPException(status_code=400, detail="OA 账号和口令都要填")

    if payload.max_scan < 1 or payload.max_scan > 200:
        raise HTTPException(status_code=400, detail="扫描数量应在 1–200 之间")

    batch_id = store.create_batch(
        conn,
        name=f"扫描 {payload.status_filter or '全部'}",
        oa_username=payload.username,
        status_filter=payload.status_filter,
        max_scan=payload.max_scan,
        created_by=username,
    )
    _running.add(batch_id)
    asyncio.create_task(_execute(batch_id, payload))

    # 不回显凭据，也不回显口令进了哪儿
    return {"batch_id": batch_id, "status": "running"}


@router.get("")
def list_all(
    conn: sqlite3.Connection = Depends(get_conn),
    username: str = Depends(auth.current_user),
) -> dict[str, object]:
    items = store.list_batches(conn)
    return {"items": items, "total": len(items)}


@router.get("/{batch_id}")
def detail(
    batch_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    username: str = Depends(auth.current_user),
) -> dict[str, object]:
    batch = store.get_batch(conn, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail=f"批次 {batch_id} 不存在")
    return {"batch": batch, "items": store.batch_items(conn, batch_id)}


@router.get("/meta/options")
def options() -> dict[str, object]:
    """启动弹窗要用的选项。状态文案与 OA 保持一致。"""
    return {
        "statuses": [
            {"value": "", "label": "全部"},
            {"value": "pending", "label": "待审批"},
            {"value": "approved", "label": "已通过"},
            {"value": "rejected", "label": "已驳回"},
        ],
        "default_user": config.OA_USERNAME,
    }
