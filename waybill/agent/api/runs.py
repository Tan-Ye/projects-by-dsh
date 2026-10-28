"""一次运行的全部事实：步骤、证据、核验、判断、自愈。

这个接口就是三层下钻的数据源：
    L1 结论 → run 本身
    L2 过程 → steps
    L3 证据 → extractions / verifications / judgments / repairs
"""

from __future__ import annotations

import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

import auth
from api.deps import get_conn

router = APIRouter(prefix="/api/runs", tags=["runs"])


def _json(value: str | None) -> object:
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


@router.get("/{run_id}")
def get_run(
    run_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    username: str = Depends(auth.current_user),
) -> dict[str, object]:
    run = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if run is None:
        raise HTTPException(status_code=404, detail=f"运行 {run_id} 不存在")

    steps = [
        dict(row)
        for row in conn.execute(
            "SELECT seq, intent, action, outcome, reason_code, reason_message,"
            " target_path, duration_ms FROM steps WHERE run_id = ? ORDER BY seq",
            (run_id,),
        )
    ]
    extractions = [
        {
            "name": row["name"],
            "payload": _json(row["payload"]),
            "sha256": row["sha256"],
        }
        for row in conn.execute(
            "SELECT name, payload, sha256 FROM extractions WHERE run_id = ?"
            # 配方放最后：它是"怎么跑的"，不是"看到了什么"，阅读顺序上靠后
            " ORDER BY CASE name WHEN 'recipe' THEN 1 ELSE 0 END, id",
            (run_id,),
        )
    ]
    verifications = [
        dict(row)
        for row in conn.execute(
            "SELECT layer, field, passed, reason_code, expected, actual"
            " FROM verifications WHERE run_id = ? ORDER BY id",
            (run_id,),
        )
    ]
    judgments = [
        dict(row)
        for row in conn.execute(
            "SELECT summary, chosen, confidence, rationale, accepted, reason"
            " FROM judgments WHERE run_id = ? ORDER BY id",
            (run_id,),
        )
    ]
    repairs = [
        {
            **dict(row),
            "old_target": _json(row["old_target"]),
            "new_target": _json(row["new_target"]),
        }
        for row in conn.execute(
            "SELECT step_seq, target_path, old_target, new_target, confidence,"
            " rationale, outcome FROM repairs WHERE run_id = ? ORDER BY id",
            (run_id,),
        )
    ]

    return {
        "run": dict(run),
        "steps": steps,
        "extractions": extractions,
        "verifications": verifications,
        "judgments": judgments,
        "repairs": repairs,
    }
