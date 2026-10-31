"""任务列表。

一条记录 = 一个任务 + 它最近一次运行。没有任务归属的 run（直接跑 run_task
产生的）也列出来，否则控制台会漏掉一半执行记录。
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

import auth
from api.deps import get_conn

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

TASK_SQL = """
SELECT t.id            AS task_id,
       t.name          AS name,
       t.recipe        AS recipe,
       t.status        AS status,
       t.attempts      AS attempts,
       t.created_at    AS created_at,
       t.finished_at   AS finished_at,
       t.last_error    AS last_error,
       r.id            AS run_id,
       r.external_ref  AS external_ref,
       r.reason_code   AS reason_code,
       r.reason_message AS reason_message,
       r.recipe_version AS recipe_version
FROM tasks t
LEFT JOIN runs r ON r.id = (
    SELECT id FROM runs WHERE task_id = t.id ORDER BY id DESC LIMIT 1
)
ORDER BY t.id DESC
"""

ORPHAN_SQL = """
SELECT NULL           AS task_id,
       task_name      AS name,
       recipe_name    AS recipe,
       status         AS status,
       1              AS attempts,
       started_at     AS created_at,
       finished_at    AS finished_at,
       reason_message AS last_error,
       id             AS run_id,
       external_ref   AS external_ref,
       reason_code    AS reason_code,
       reason_message AS reason_message,
       recipe_version AS recipe_version
FROM runs
WHERE task_id IS NULL
ORDER BY id DESC
"""


@router.get("")
def list_tasks(
    include_orphans: bool = False,
    conn: sqlite3.Connection = Depends(get_conn),
    username: str = Depends(auth.current_user),
) -> dict[str, object]:
    """任务列表。

    include_orphans：是否连"没有任务归属的运行"一起列。
    单条调试（run_task）和评测（evaluate）产生的都是无主运行，
    默认不显示——否则任务列表会被几十条评测记录淹掉。
    """
    rows = [dict(row) for row in conn.execute(TASK_SQL)]
    if include_orphans:
        rows.extend(dict(row) for row in conn.execute(ORPHAN_SQL))
    rows.sort(key=lambda row: (row["run_id"] or 0), reverse=True)
    return {"items": rows, "total": len(rows)}
