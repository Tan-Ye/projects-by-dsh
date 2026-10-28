"""按任务跑一次：登录 → 读 OA → 落证据 → 写财务 → 记状态。

    python -m scripts.run_task tasks/t1.json

调试用的入口：不入队，直接跑，输出直接打屏幕上。
批量投递用 scripts/enqueue.py，消费队列用 scripts/worker.py。

OA 账号从环境变量取（OA_USERNAME / OA_PASSWORD），只在这个调试入口使用；
控制台走的是"弹窗里人手填"。

退出码：
    0  成功（凭证已建好且核验一致）
    1  执行失败（浏览器断言/超时）
    2  配置错误（缺配方、缺参数）—— 批处理时不要重试
    3  映射或核验没过，需要人工
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

import config
import store
from browser.replay import StepFailed
from browser.session import SessionError, default_credentials, open_session
from flows.execute import execute_task


async def run(task_path_name: str) -> int:
    task_path = config.AGENT_DIR / task_path_name
    if not task_path.is_file():
        print(f"任务文件不存在: {task_path}")
        return 2

    task = json.loads(task_path.read_text(encoding="utf-8"))

    store.init_db()
    conn = store.connect()
    session = None
    try:
        try:
            session = await open_session(*default_credentials())
            status, message = await execute_task(
                conn,
                task_id=None,
                task_name=task.get("name", task_path.stem),
                recipe_name=task["recipe"],
                inputs=task.get("inputs", {}),
                page=session.page,
            )
        except StepFailed as exc:
            print(f"配置错误 [{exc.code}] {exc.message}")
            return 2
        except SessionError as exc:
            print(f"会话错误 [{exc.code}] {exc.message}")
            return 1
    finally:
        if session is not None:
            await session.close()
        conn.close()

    print("\n" + message)
    return {"succeeded": 0, "waiting_human": 3}.get(status, 1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("task", help="任务 JSON 路径；配方由 task.recipe 决定")
    args = parser.parse_args()
    return asyncio.run(run(args.task))


if __name__ == "__main__":
    sys.exit(main())
