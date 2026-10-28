"""评测夹具：把库重置成某个任务的起点。

只清业务数据（凭证）；用户、部门、科目、成本中心属于"系统配置"，保留。

T3 需要预置一张**已入账**的凭证——它的作用是让 agent 撞上"单号已存在"，
而且要撞在"已提交"上：草稿可以覆盖，已入账的不能。
"""

from __future__ import annotations

import sqlite3

from .timefmt import now_str

# 顺序有意义：先删子表再删主表（外键 ON DELETE CASCADE 也兜得住，但不依赖它）
VOUCHER_TABLES = ("voucher_errors", "voucher_lines", "vouchers")


def reset(conn: sqlite3.Connection) -> None:
    """清空凭证相关数据。"""
    with conn:
        for table in VOUCHER_TABLES:
            conn.execute(f"DELETE FROM {table}")
        # 自增 id 一起重置，夹具才算真正可复现
        conn.execute(
            "DELETE FROM sqlite_sequence WHERE name IN"
            " ('vouchers', 'voucher_lines', 'voucher_errors')"
        )


def _seed_t3(conn: sqlite3.Connection) -> dict[str, object]:
    """T3 起点：BX-2024-0912 已经入账。"""
    ts = now_str()
    with conn:
        cur = conn.execute(
            "INSERT INTO vouchers (voucher_no, external_ref, voucher_date, summary,"
            " dept_code, attachment_count, status, created_by, created_at, saved_at,"
            " submitted_at, submitted_by, approved_at, approved_by)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "PZ-2024-0001",
                "BX-2024-0912",
                "2024-09-10",
                "客户拜访交通费",
                "MKT",
                1,
                "submitted",
                "maker",
                ts,
                ts,
                ts,
                "maker",
                ts,
                "checker",
            ),
        )
        voucher_id = cur.lastrowid
        conn.execute(
            "INSERT INTO voucher_lines (voucher_id, seq, account_code, cost_center,"
            " debit_cents, summary) VALUES (?,?,?,?,?,?)",
            (voucher_id, 1, "6601.03", "CC-MKT-01", 12860, "客户拜访打车费"),
        )
    return {"vouchers": 1, "external_ref": "BX-2024-0912", "status": "submitted"}


FIXTURES = {
    "T3": _seed_t3,
}


def apply(conn: sqlite3.Connection, name: str) -> dict[str, object]:
    """重置 + 应用夹具。未知名字抛 KeyError，由调用方翻译成 4xx。"""
    reset(conn)
    return FIXTURES[name](conn)
