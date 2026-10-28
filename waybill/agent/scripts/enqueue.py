"""把任务文件入队。

    python -m scripts.enqueue tasks/t1.json
    python -m scripts.enqueue tasks/          # 整个目录

同一个任务重复入队会被幂等键挡掉，不会跑两遍。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import config
import store


def enqueue_file(conn, path: Path) -> int | None:
    """读任务文件并入队。返回 task_id；已存在返回 None。"""
    task = json.loads(path.read_text(encoding="utf-8"))
    return store.enqueue_task(
        conn,
        name=task.get("name", path.stem),
        recipe=task["recipe"],
        inputs=task.get("inputs", {}),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="任务文件或目录")
    args = parser.parse_args()

    target = config.AGENT_DIR / args.path
    if not target.exists():
        print(f"路径不存在: {target}")
        return 2

    files = sorted(target.glob("*.json")) if target.is_dir() else [target]

    store.init_db()
    conn = store.connect()
    try:
        for path in files:
            task_id = enqueue_file(conn, path)
            state = f"入队 id={task_id}" if task_id else "已存在，跳过"
            print(f"{path.name}: {state}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
