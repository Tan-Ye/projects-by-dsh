"""跑一批：登录 → 扫描 → 去重 → 逐单处理。

控制台和命令行共用这一份。整批共用一个会话：换单号只改 URL，不重新登录。

凭据只在这里过一手：不写库、不打日志、不进批次记录。
"""

from __future__ import annotations

import sqlite3

import store
from browser.session import SessionError, open_session
from flows.discover import DiscoverError, discover
from flows.execute import execute_task

TASK_STATUS = {"succeeded": "succeeded", "waiting_human": "waiting_human", "failed": "failed"}


async def run_batch(
    *,
    batch_id: int,
    username: str,
    password: str,
    status_filter: str,
    max_scan: int,
) -> None:
    """执行一个已建好的批次。异常一律落到批次状态上，不往外抛。

    自己开连接：控制台的连接是请求级的，批次活得比请求久。
    """
    conn: sqlite3.Connection = store.connect()
    session = None
    try:
        session = await open_session(username, password)
        page = await session.require_page()

        result = await discover(
            conn,
            page=page,
            batch_id=batch_id,
            status_filter=status_filter,
            max_scan=max_scan,
        )
        print(
            f"[批次 {batch_id}] 扫描 {result['scanned']} 条 → 重复 {result['duplicated']} · "
            f"已有 {result['skipped']} · 入队 {result['queued']}"
        )

        for task_id, doc_no in result["tasks"]:
            task_status, message = await execute_task(
                conn,
                task_id=task_id,
                task_name=f"read_{doc_no}",
                recipe_name="oa_read_doc",
                inputs={"doc_no": doc_no},
                page=page,
            )
            last_line = message.splitlines()[-1] if message else ""
            store.finish_task(
                conn,
                task_id,
                status=TASK_STATUS.get(task_status, "failed"),
                error=None if task_status == "succeeded" else message,
            )
            store.set_batch_item_outcome(
                conn, batch_id, doc_no, outcome=task_status, note=last_line
            )
            print(f"[批次 {batch_id}] {doc_no} → {task_status}")

        store.finish_batch(conn, batch_id, status="succeeded")
    except SessionError as exc:
        store.finish_batch(
            conn, batch_id, status="failed", reason_code=exc.code, reason_message=exc.message
        )
    except DiscoverError as exc:
        store.finish_batch(
            conn, batch_id, status="failed", reason_code=exc.code, reason_message=exc.message
        )
    except Exception as exc:  # 批次不能把控制台带崩
        store.finish_batch(
            conn, batch_id, status="failed", reason_code="BATCH_CRASHED",
            reason_message=repr(exc),
        )
    finally:
        if session is not None:
            await session.close()
        conn.close()
