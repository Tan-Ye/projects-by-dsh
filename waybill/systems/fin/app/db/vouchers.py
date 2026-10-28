"""凭证：表头、明细、校验错误、状态流转。

派生字段（validated / total_cents）库里没有列，查询时现算。
"""

from __future__ import annotations

import sqlite3
from typing import cast

from .models import (
    VoucherDetail,
    VoucherErrorRow,
    VoucherInput,
    VoucherLineInput,
    VoucherLineRow,
    VoucherPage,
    VoucherRow,
)
from .timefmt import now_str


def create_voucher(
    conn: sqlite3.Connection,
    data: VoucherInput,
    created_by: str,
    errors: list[VoucherErrorRow],
) -> int:
    """建一张凭证（表头 + 明细 + 校验错误），返回新 id。

    表头、明细、错误在**同一个事务**里写，中途失败整体回滚。
    `seq` 按数组顺序生成（下标 + 1）。
    `external_ref` 重复时不捕获 IntegrityError，让路由层统一转 409。
    建单即首次保存，`saved_at` 直接写成当前时间。
    """
    now = now_str()
    with conn:
        cur = conn.execute(
            "INSERT INTO vouchers (external_ref, voucher_date, summary, dept_code,"
            " attachment_count, status, created_by, created_at, saved_at)"
            " VALUES (?,?,?,?,?,'draft',?,?,?)",
            (
                data["external_ref"],
                data["voucher_date"],
                data["summary"],
                data["dept_code"],
                data["attachment_count"],
                created_by,
                now,
                now,
            ),
        )
        # lastrowid 的类型是 int | None：插入语句一定有，但类型系统不这么认为
        if cur.lastrowid is None:
            raise RuntimeError("建单失败：没拿到 lastrowid")
        voucher_id = int(cur.lastrowid)
        _insert_lines(conn, voucher_id, data["lines"])
        _insert_errors(conn, voucher_id, errors)
    return voucher_id


def replace_voucher(
    conn: sqlite3.Connection,
    voucher_id: int,
    data: VoucherInput,
    errors: list[VoucherErrorRow],
) -> None:
    """用新内容覆盖一张草稿：表头、全部明细、校验错误、saved_at。

    明细是**整单替换**：DELETE 旧行后按数组顺序重插，seq 重排；
    整个替换包在一个事务里，避免"删完插失败"留下空单。
    """
    with conn:
        conn.execute(
            "UPDATE vouchers SET voucher_date = ?, summary = ?, dept_code = ?,"
            " attachment_count = ?, saved_at = ? WHERE id = ?",
            (
                data["voucher_date"],
                data["summary"],
                data["dept_code"],
                data["attachment_count"],
                now_str(),
                voucher_id,
            ),
        )
        conn.execute("DELETE FROM voucher_lines WHERE voucher_id = ?", (voucher_id,))
        conn.execute("DELETE FROM voucher_errors WHERE voucher_id = ?", (voucher_id,))
        _insert_lines(conn, voucher_id, data["lines"])
        _insert_errors(conn, voucher_id, errors)


def get_voucher(conn: sqlite3.Connection, voucher_id: int) -> VoucherDetail | None:
    """取详情：表头 + 明细（按 seq）+ 最近一次校验错误 + 两个派生字段。

    `validated` 和 `total_cents` 库里没有列，这里现算；找不到返回 None。
    """
    row = conn.execute(
        "SELECT id, voucher_no, external_ref, voucher_date, summary, dept_code,"
        " attachment_count, status, created_by, created_at, saved_at,"
        " submitted_at, submitted_by, approved_at, approved_by, review_note"
        " FROM vouchers WHERE id = ?",
        (voucher_id,),
    ).fetchone()
    if row is None:
        return None

    # 列名与 VoucherRow 逐一对齐
    voucher = cast(VoucherRow, dict(row))
    lines = [
        cast(VoucherLineRow, dict(r))
        for r in conn.execute(
            "SELECT id, voucher_id, seq, account_code, cost_center, debit_cents, summary"
            " FROM voucher_lines WHERE voucher_id = ? ORDER BY seq",
            (voucher_id,),
        ).fetchall()
    ]
    errors = [
        cast(VoucherErrorRow, dict(r))
        for r in conn.execute(
            "SELECT field, code, message FROM voucher_errors WHERE voucher_id = ? ORDER BY id",
            (voucher_id,),
        ).fetchall()
    ]

    detail = {
        **voucher,
        "lines": lines,
        "errors": errors,
        # 保存过、且最近一次保存没有错误行，才算校验通过
        "validated": voucher["saved_at"] is not None and not errors,
        "total_cents": sum(line["debit_cents"] for line in lines),
    }
    return cast(VoucherDetail, detail)


def list_vouchers(
    conn: sqlite3.Connection,
    status: str | None = None,
    external_ref: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> VoucherPage:
    """按状态 / 外部单号筛选并分页，返回总数和当前页。

    排序固定 `created_at DESC, id DESC`——同一秒创建的记录靠 id 兜底，分页才稳定。
    `total` 按筛选条件单独 COUNT。
    """
    where: list[str] = []
    params: list[object] = []
    if status:
        where.append("status = ?")
        params.append(status)
    if external_ref:
        where.append("external_ref = ?")
        params.append(external_ref)
    clause = (" WHERE " + " AND ".join(where)) if where else ""

    total = conn.execute(
        f"SELECT COUNT(*) AS n FROM vouchers{clause}", params
    ).fetchone()["n"]
    rows = conn.execute(
        "SELECT id, voucher_no, external_ref, voucher_date, summary, dept_code,"
        " attachment_count, status, created_by, created_at, saved_at,"
        " submitted_at, submitted_by, approved_at, approved_by, review_note"
        f" FROM vouchers{clause} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
        [*params, page_size, (page - 1) * page_size],
    ).fetchall()

    # 列名与 VoucherRow 逐一对齐
    items = [cast(VoucherRow, dict(r)) for r in rows]
    return {"total": int(total), "page": page, "page_size": page_size, "items": items}


def next_voucher_no(conn: sqlite3.Connection, voucher_date: str) -> str:
    """生成 `PZ-YYYYMMDD-0001` 形式的凭证号，序号按当天递增。

    并发下可能撞号：`voucher_no` 上有 UNIQUE，调用方接住 IntegrityError 重试一次即可。
    """
    prefix = "PZ-" + voucher_date.replace("-", "")
    row = conn.execute(
        "SELECT MAX(voucher_no) AS m FROM vouchers WHERE voucher_no LIKE ?",
        (prefix + "-%",),
    ).fetchone()
    last = row["m"] if row else None
    seq = int(str(last).rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}-{seq:04d}"


def mark_pending(
    conn: sqlite3.Connection,
    voucher_id: int,
    submitted_by: str,
) -> None:
    """制单人提交审批：draft → pending，记提交人。"""
    with conn:
        conn.execute(
            "UPDATE vouchers SET status = 'pending', submitted_at = ?, submitted_by = ?,"
            " review_note = NULL WHERE id = ?",
            (now_str(), submitted_by, voucher_id),
        )


def mark_approved(
    conn: sqlite3.Connection,
    voucher_id: int,
    voucher_no: str,
    approved_by: str,
) -> None:
    """复核通过：pending → submitted，分配凭证号并记复核人。"""
    with conn:
        conn.execute(
            "UPDATE vouchers SET status = 'submitted', voucher_no = ?,"
            " approved_at = ?, approved_by = ? WHERE id = ?",
            (voucher_no, now_str(), approved_by, voucher_id),
        )


def mark_rejected(
    conn: sqlite3.Connection,
    voucher_id: int,
    review_note: str,
) -> None:
    """复核驳回：pending → draft，把意见写回单据，制单人改完可以重新提交。"""
    with conn:
        conn.execute(
            "UPDATE vouchers SET status = 'draft', review_note = ?,"
            " submitted_at = NULL, submitted_by = NULL WHERE id = ?",
            (review_note, voucher_id),
        )


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

def _insert_lines(
    conn: sqlite3.Connection,
    voucher_id: int,
    lines: list[VoucherLineInput],
) -> None:
    """按数组顺序写明细，seq 从 1 开始——seq 是位置，不是调用方给的值。"""
    if not lines:
        return
    conn.executemany(
        "INSERT INTO voucher_lines (voucher_id, seq, account_code, cost_center,"
        " debit_cents, summary) VALUES (?,?,?,?,?,?)",
        [
            (voucher_id, i, line["account_code"], line["cost_center"],
             line["debit_cents"], line.get("summary", ""))
            for i, line in enumerate(lines, start=1)
        ],
    )


def _insert_errors(
    conn: sqlite3.Connection,
    voucher_id: int,
    errors: list[VoucherErrorRow],
) -> None:
    """写入最近一次校验的错误；空列表表示校验通过。"""
    if not errors:
        return
    now = now_str()
    conn.executemany(
        "INSERT INTO voucher_errors (voucher_id, field, code, message, created_at)"
        " VALUES (?,?,?,?,?)",
        [(voucher_id, e["field"], e["code"], e["message"], now) for e in errors],
    )
