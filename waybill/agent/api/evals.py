"""评测结果：列表与详情。

结果由 scripts/evaluate.py 写入，控制台只读。
页面上能对比两次评测——"改完之后有没有变差"是这套东西存在的唯一理由。
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

import auth
import store
from api.deps import get_conn

router = APIRouter(prefix="/api/evals", tags=["evals"])


@router.get("")
def list_all(
    conn: sqlite3.Connection = Depends(get_conn),
    username: str = Depends(auth.current_user),
) -> dict[str, object]:
    items = store.list_evals(conn)
    return {"items": items, "total": len(items)}


@router.get("/{eval_id}")
def detail(
    eval_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    username: str = Depends(auth.current_user),
) -> dict[str, object]:
    item = store.get_eval(conn, eval_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"评测 {eval_id} 不存在")
    return item
