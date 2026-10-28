"""跑一批：登录 → 扫描 → 去重 → 逐单处理。

    python -m scripts.run_batch --status pending --max 5
    python -m scripts.run_batch --status "" --max 3      # 全部状态

控制台走 /api/batches，和这里是同一份流程（flows/batch.py）。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

import config
import store
from flows.batch import run_batch


async def run(username: str, password: str, status_filter: str, max_scan: int) -> int:
    store.init_db()
    conn = store.connect()
    try:
        batch_id = store.create_batch(
            conn,
            name=f"扫描 {status_filter or '全部'}",
            oa_username=username,
            status_filter=status_filter,
            max_scan=max_scan,
            created_by="cli",
        )
        batch = store.get_batch(conn, batch_id)
        if batch is not None:
            print(f"批次 {batch_id} 开始")
    finally:
        conn.close()

    await run_batch(
        batch_id=batch_id,
        username=username,
        password=password,
        status_filter=status_filter,
        max_scan=max_scan,
    )

    conn = store.connect()
    try:
        batch = store.get_batch(conn, batch_id)
        items = store.batch_items(conn, batch_id)
    finally:
        conn.close()

    if batch is None:
        print("批次记录丢了")
        return 1

    print(
        f"\n批次 {batch_id} {batch['status']}：扫描 {batch['scanned']} · "
        f"重复 {batch['duplicated']} · 已有 {batch['skipped']} · 入队 {batch['queued']}"
    )
    for item in items:
        print(f"  {item['doc_no']}  {item['outcome']}")
    return 0 if batch["status"] == "succeeded" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", default=config.OA_USERNAME, help="OA 账号")
    parser.add_argument("--password", default=config.OA_PASSWORD, help="OA 口令")
    parser.add_argument("--status", default="", help="列表筛选：pending / approved / rejected；空=全部")
    parser.add_argument("--max", type=int, default=5, help="最多扫描多少条")
    args = parser.parse_args()

    started = time.perf_counter()
    code = asyncio.run(run(args.user, args.password, args.status, args.max))
    print(f"\n耗时 {time.perf_counter() - started:.1f}s，退出码 {code}")
    return code


if __name__ == "__main__":
    sys.exit(main())
