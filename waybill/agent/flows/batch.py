"""跑一批：登录 → 扫描 → 去重 → 逐单处理。

控制台和命令行共用这一份。整批共用一个会话：换单号只改 URL，不重新登录。

凭据只在这里过一手：不写库、不打日志、不进批次记录。
"""

from __future__ import annotations

import sqlite3

import store
from browser.repair import make_repairer
from browser.replay import RepairHook
from browser.session import SessionError, open_session
from flows.discover import DiscoverError, discover
from flows.execute import execute_task
from llm import LlmClient

TASK_STATUS = {"succeeded": "succeeded", "waiting_human": "waiting_human", "failed": "failed"}


def _build_repairer() -> tuple[RepairHook | None, LlmClient | None]:
    """整批共用一个修复器。没有 key 就退化成"不自愈"，主流程照跑。"""
    try:
        client = LlmClient.from_config()
    except RuntimeError as exc:
        print(f"[批次] 自愈不可用：{exc}")
        return None, None
    return make_repairer(client), client


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
    hook, llm = _build_repairer()

    try:
        session = await open_session(username, password)
        page = await session.require_page()

        result = await discover(
            conn,
            page=page,
            batch_id=batch_id,
            status_filter=status_filter,
            max_scan=max_scan,
            repair=hook,
        )
        print(
            f"[批次 {batch_id}] 扫描 {result['scanned']} 条 → 重复 {result['duplicated']} · "
            f"已有 {result['skipped']} · 入队 {result['queued']}"
        )

        # 一条单子出问题不能带崩整批：异常按单记 failed，继续下一单
        for task_id, doc_no in result["tasks"]:
            task_status, message = await _run_one(
                conn, batch_id, task_id, doc_no, page, hook
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
        if llm is not None:
            await llm.aclose()
        conn.close()


async def _run_one(
    conn: sqlite3.Connection,
    batch_id: int,
    task_id: int,
    doc_no: str,
    page: object,
    hook: RepairHook | None,
) -> tuple[str, str]:
    """跑一条单号，任何异常都收敛成 failed，不外抛。"""
    try:
        task_status, message = await execute_task(
            conn,
            task_id=task_id,
            task_name=f"read_{doc_no}",
            recipe_name="oa_read_doc",
            inputs={"doc_no": doc_no},
            page=page,  # type: ignore[arg-type]
            repair=hook,
        )
    except Exception as exc:  # 财务接口抖动、浏览器异常……都只影响这一单
        task_status = "failed"
        message = f"[BATCH_ITEM_CRASHED] {exc!r}"

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
    return task_status, message
