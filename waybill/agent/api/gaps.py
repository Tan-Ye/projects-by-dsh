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
    # rationale 要取"最近一次"的：MAX(rationale) 是字典序，不是时间序，
    # 那样页面上显示的可能是很早以前那条不相干的理由。
    rows = conn.execute(
        "SELECT j.summary,"
        " COUNT(*) AS count,"
        " MAX(j.created_at) AS last_at,"
        " (SELECT j2.rationale FROM judgments j2"
        "   WHERE j2.summary = j.summary AND j2.accepted = 0"
        "   ORDER BY j2.id DESC LIMIT 1) AS rationale,"
        " (SELECT j3.reason FROM judgments j3"
        "   WHERE j3.summary = j.summary AND j3.accepted = 0"
        "   ORDER BY j3.id DESC LIMIT 1) AS reason"
        " FROM judgments j WHERE j.accepted = 0"
        " GROUP BY j.summary"
        " ORDER BY count DESC, j.summary"
    ).fetchall()

    items = [dict(row) for row in rows]
    return {
        "items": items,
        "total": len(items),
        "affected": sum(int(item["count"]) for item in items),
    }
