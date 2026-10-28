"""数据行的形状。

SQLite 没有 boolean，布尔列在 Python 里就是 int（0/1），所以这里标 int 而不是 bool。
"""

from __future__ import annotations

from typing import TypedDict


class UserRow(TypedDict):
    """users 表的一行。"""

    username: str
    password_hash: str
    display_name: str
    role: str
    is_active: int


class AccountRow(TypedDict):
    """accounts 表的一行（科目树节点）。"""

    code: str
    name: str
    parent_code: str | None
    level: int
    is_leaf: int
    is_active: int
    sort: int


class DepartmentRow(TypedDict):
    """departments 表的一行。"""

    code: str
    name: str
    is_active: int


class CostCenterRow(TypedDict):
    """cost_centers 表的一行。"""

    code: str
    name: str
    dept_code: str
    is_default: int
    is_active: int


class SessionRow(TypedDict):
    """sessions 表的一行。"""

    token: str
    username: str
    created_at: str
    expires_at: int


class VoucherLineRow(TypedDict):
    """voucher_lines 表的一行。"""

    id: int
    voucher_id: int
    seq: int
    account_code: str
    cost_center: str
    debit_cents: int
    summary: str


class VoucherRow(TypedDict):
    """vouchers 表的一行。"""

    id: int
    voucher_no: str | None          # 入账通过时才分配
    external_ref: str
    voucher_date: str
    summary: str
    dept_code: str
    attachment_count: int
    status: str                     # draft / pending / submitted / voided
    created_by: str
    created_at: str
    saved_at: str | None            # None 表示从没保存过
    submitted_at: str | None        # 提交审批时间
    submitted_by: str | None
    approved_at: str | None         # 复核通过时间
    approved_by: str | None
    review_note: str | None         # 驳回意见


class VoucherErrorRow(TypedDict):
    """voucher_errors 表的一行。"""

    field: str                      # 如 lines[1].account_code
    code: str                       # 如 ACCOUNT_NOT_LEAF
    message: str


class VoucherLineInput(TypedDict):
    """写入明细的形状。没有 id / seq —— seq 由数组顺序生成。"""

    account_code: str
    cost_center: str
    debit_cents: int
    summary: str


class VoucherInput(TypedDict):
    """写入整张单据的形状。路由层用 Pydantic 模型的 model_dump() 得到它。"""

    external_ref: str
    voucher_date: str
    summary: str
    dept_code: str
    attachment_count: int
    lines: list[VoucherLineInput]


class VoucherDetail(VoucherRow):
    """详情：行数据 + 明细 + 错误 + 两个派生字段。

    validated 和 total_cents 库里没有列，查询时现算。
    """

    lines: list[VoucherLineRow]
    errors: list[VoucherErrorRow]
    validated: bool
    total_cents: int


class VoucherPage(TypedDict):
    """分页结果。"""

    total: int
    page: int
    page_size: int
    items: list[VoucherRow]
