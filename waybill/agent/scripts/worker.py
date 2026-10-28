"""队列消费者：领一条、跑一条、回写状态。

    python -m scripts.worker              # 清空队列后退出
    python -m scripts.worker --limit 1    # 只跑一条，调试用

一条任务出问题不能让 worker 崩掉——异常一律记进 tasks.last_error，
然后继续领下一条。

注意：这是"逐单"入口，每条任务各自登一次 OA。
批次模式（登录一次跑多单）在 scripts/run_batch.py。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys

import store
from browser.replay import StepFailed
from browser.session import SessionError, default_credentials, open_session
from flows.execute import execute_task


async def _execute(conn: sqlite3.Connection, task: dict[str, object]) -> tuple[str, str]:
    """开一个会话跑一条任务，跑完就关。"""
    session = await open_session(*default_credentials())
    try:
        return await execute_task(
            conn,
            task_id=int(str(task["id"])),
            task_name=str(task["name"]),
            recipe_name=str(task["recipe"]),
            inputs=json.loads(str(task["inputs"])),
            page=session.page,
        )
    finally:
        await session.close()


def run_one(conn: sqlite3.Connection, task: dict[str, object]) -> int:
    """跑一条任务并把状态写回队列。返回退出码。"""
    task_id = int(str(task["id"]))
    try:
        status, message = asyncio.run(_execute(conn, task))
    except StepFailed as exc:
        # 配置错误：重试也没用，直接判失败并记原因
        store.finish_task(
            conn, task_id, status="failed", error=f"{exc.code}: {exc.message}"
        )
        print(f"任务 {task_id} 配置错误 [{exc.code}] {exc.message}")
        return 2
    except SessionError as exc:
        store.finish_task(conn, task_id, status="failed", error=f"{exc.code}: {exc.message}")
        print(f"任务 {task_id} 会话错误 [{exc.code}] {exc.message}")
        return 1
    except Exception as exc:  # worker 不能因为一条任务崩掉
        store.finish_task(conn, task_id, status="failed", error=repr(exc))
        print(f"任务 {task_id} 异常：{exc!r}")
        return 1

    store.finish_task(
        conn,
        task_id,
        status=status,
        error=None if status == "succeeded" else message,
    )
    print(f"任务 {task_id}: {message}")
    return {"succeeded": 0, "waiting_human": 3}.get(status, 1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="最多跑几条，0 表示跑空为止")
    args = parser.parse_args()

    store.init_db()
    conn = store.connect()
    processed = 0
    try:
        while args.limit == 0 or processed < args.limit:
            task = store.claim_task(conn)
            if task is None:
                print("队列已空")
                break
            run_one(conn, task)
            processed += 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
