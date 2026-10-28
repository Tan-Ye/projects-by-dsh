"""人工闸门：等人工处理的任务，以及两个处理动作。

动作只有两个：
    retry    放回队列，让 agent 再跑一次
    resolve  人已经处理完（通常是去财务系统里手工补齐）

两者都写 gate_actions——谁、什么时候、做了什么，必须留痕。
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import auth
import store
from api.deps import get_conn

router = APIRouter(prefix="/api/gate", tags=["gate"])


class ResolveRequest(BaseModel):
    note: str


@router.get("")
def list_gate(
    conn: sqlite3.Connection = Depends(get_conn),
    username: str = Depends(auth.current_user),
) -> dict[str, object]:
    items = store.list_gate(conn)
    return {"items": items, "total": len(items)}


@router.post("/{task_id}/retry")
def retry(
    task_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    username: str = Depends(auth.current_user),
) -> dict[str, object]:
    if not store.retry_task(conn, task_id, actor=username):
        raise HTTPException(status_code=409, detail="任务不在可重跑的状态")
    return {"ok": True, "status": "pending"}


@router.post("/{task_id}/resolve")
def resolve(
    task_id: int,
    payload: ResolveRequest,
    conn: sqlite3.Connection = Depends(get_conn),
    username: str = Depends(auth.current_user),
) -> dict[str, object]:
    note = payload.note.strip()
    if not note:
        # 备注必填：没有备注的"已处理"等于没留下任何依据
        raise HTTPException(status_code=400, detail="请填写处理说明")

    if not store.resolve_task(conn, task_id, actor=username, note=note):
        raise HTTPException(status_code=409, detail="任务不在待处理状态")
    return {"ok": True, "status": "resolved"}


@router.get("/{task_id}/history")
def history(
    task_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    username: str = Depends(auth.current_user),
) -> dict[str, object]:
    return {"items": store.gate_history(conn, task_id)}
