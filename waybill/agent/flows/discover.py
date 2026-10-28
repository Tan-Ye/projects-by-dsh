"""发现：把待办列表里的单号扫出来，去重，生成任务。

这一层是"配方产出"的第二个解释器：
    voucher 流程  把 doc/lines 解释成一张凭证
    discover 流程 把 rows 解释成一批任务

自己做的事：
    1. 按页跑 oa_discover 配方（页码作为参数，URL 驱动）
    2. 去重：批内重复的单号只留第一次
    3. 跳过：财务系统里已有该单号的凭证
    4. 入队：剩下的每条生成一个任务，并记进 batch_items
"""

from __future__ import annotations

import re
import sqlite3
from typing import TypedDict

import httpx
import store
from browser.replay import RepairHook, load_recipe, render, replay
from playwright.async_api import Page

import config

RECIPE = "oa_discover"
MAX_PAGES = 50  # 防御：分页解析出问题时不要死循环

_HEADER_TOTAL = re.compile(r"共\s*(\d+)\s*条")
_PAGER_PAGES = re.compile(r"第\s*\d+\s*/\s*(\d+)\s*页")


class DiscoverResult(TypedDict):
    scanned: int
    duplicated: int
    skipped: int
    queued: int
    duplicates: list[str]
    existing: list[str]
    tasks: list[tuple[int, str]]  # (task_id, doc_no)


def _parse_total(header: str) -> int:
    match = _HEADER_TOTAL.search(header)
    return int(match.group(1)) if match else 0


def _parse_pages(pager: str) -> int:
    match = _PAGER_PAGES.search(pager)
    return int(match.group(1)) if match else 1


async def _exists_in_finance(doc_no: str) -> bool:
    """财务系统里有没有这个外部单号的凭证。以财务为准，不查自己的库。"""
    async with httpx.AsyncClient(base_url=config.FIN_BASE_URL, timeout=15.0) as client:
        resp = await client.get(f"/api/state/{doc_no}")
        if resp.status_code == 404:
            return False
        resp.raise_for_status()
        return True


async def collect_docs(
    page: Page,
    *,
    status_filter: str,
    max_scan: int,
    repair: RepairHook | None = None,
) -> tuple[list[str], int]:
    """翻页收集单号。返回 (单号列表, 列表里读到的总条数)。"""
    recipe = load_recipe(RECIPE)
    docs: list[str] = []
    total = 0
    page_no = 1
    pages = 1

    while page_no <= pages and len(docs) < max_scan and page_no <= MAX_PAGES:
        steps = render(recipe["steps"], {"status": status_filter, "page": str(page_no)})
        result = await replay(recipe, steps, repair=repair, page=page)
        if not result["ok"]:
            raise DiscoverError(
                result["reason_code"] or "DISCOVER_FAILED",
                f"扫描第 {page_no} 页失败：{result['reason_message']}",
            )

        outputs = result["outputs"]
        rows = outputs.get("rows") or []
        total = _parse_total(str(outputs.get("header", "")))
        pages = _parse_pages(str(outputs.get("pager", "")))

        for row in rows:
            doc_no = str(row.get("单号", "")).strip()
            if doc_no:
                docs.append(doc_no)

        page_no += 1

    return docs[:max_scan], total


class DiscoverError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


async def discover(
    conn: sqlite3.Connection,
    *,
    page: Page,
    batch_id: int,
    status_filter: str,
    max_scan: int,
    repair: RepairHook | None = None,
) -> DiscoverResult:
    """扫描 → 去重 → 跳过已有 → 入队。全过程记进 batch_items。"""
    docs, total = await collect_docs(
        page, status_filter=status_filter, max_scan=max_scan, repair=repair
    )

    seen: set[str] = set()
    duplicates: list[str] = []
    existing: list[str] = []
    tasks: list[tuple[int, str]] = []
    queued = 0

    for doc_no in docs:
        if doc_no in seen:
            duplicates.append(doc_no)
            store.add_batch_item(
                conn, batch_id, doc_no=doc_no, outcome="duplicate", note="本批内重复"
            )
            continue
        seen.add(doc_no)

        if await _exists_in_finance(doc_no):
            existing.append(doc_no)
            store.add_batch_item(
                conn, batch_id, doc_no=doc_no, outcome="existing", note="财务已有凭证"
            )
            continue

        task_id = store.enqueue_task(
            conn,
            name=f"read_{doc_no}",
            recipe="oa_read_doc",
            inputs={"doc_no": doc_no},
            batch_id=batch_id,
        )
        if task_id is None:
            # 队列里已有同单号任务（幂等键命中）：不算新任务，但也要留下记录
            store.add_batch_item(
                conn, batch_id, doc_no=doc_no, outcome="duplicate", note="队列里已存在"
            )
            duplicates.append(doc_no)
            continue

        queued += 1
        tasks.append((task_id, doc_no))
        store.add_batch_item(
            conn, batch_id, doc_no=doc_no, outcome="queued", task_id=task_id
        )

    store.update_batch_counts(
        conn,
        batch_id,
        scanned=len(docs),
        duplicated=len(duplicates),
        skipped=len(existing),
        queued=queued,
    )

    # 账要能闭合：读到的 = 重复 + 跳过 + 入队
    if len(docs) != len(duplicates) + len(existing) + queued:
        raise DiscoverError(
            "BATCH_ACCOUNTING_MISMATCH",
            f"数量对不上：读到 {len(docs)}，重复 {len(duplicates)}，"
            f"跳过 {len(existing)}，入队 {queued}",
        )

    return DiscoverResult(
        scanned=len(docs),
        duplicated=len(duplicates),
        skipped=len(existing),
        queued=queued,
        duplicates=duplicates,
        existing=existing,
        tasks=tasks,
    )
