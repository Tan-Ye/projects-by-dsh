"""科目缺口：agent 卡住时，把"缺什么"整理成人能看的一句话。

agent 不改科目表——那是财务系统的配置，加科目要走那边的流程。
它只负责把材料备好：哪些摘要没定下来、涉及几单、模型当时怎么想的。
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

import auth
from api.deps import get_conn

router = APIRouter(prefix="/api/gaps", tags=["gaps"])


@router.get("")
def gaps(
    conn: sqlite3.Connection = Depends(get_conn),
    username: str = Depends(auth.current_user),
) -> dict[str, object]:
    rows = conn.execute(
        "SELECT summary,"
        " COUNT(*) AS count,"
        " MAX(created_at) AS last_at,"
        " MAX(rationale) AS rationale,"
        " MAX(reason) AS reason"
        " FROM judgments WHERE accepted = 0"
        " GROUP BY summary"
        " ORDER BY count DESC, summary"
    ).fetchall()

    items = [dict(row) for row in rows]
    return {"items": items, "total": len(items), "affected": sum(item["count"] for item in items)}
