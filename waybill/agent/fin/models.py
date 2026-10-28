"""财务 API 的契约类型。

与 docs/03-finance.md、前端 systems/fin/web/src/services/*/interface.ts 一一对应。
改一处就要改三处：后端 Pydantic、前端 interface、这里。

名字带来源（fin_），所以它不会变成第二个垃圾场——
看到这个文件就知道它归属财务系统，不是"全项目公用类型"。

TypedDict 只在静态检查时生效，运行时不校验。所以 HTTP 响应转具体类型的
那些 cast 都在 fin_client 里，且每条都写了理由。
"""

from __future__ import annotations

from typing import TypedDict


class Department(TypedDict):
    """GET /api/meta/departments 的一项。"""

    code: str
    name: str
    is_active: int


class CostCenter(TypedDict):
    """GET /api/meta/cost-centers 的一项。"""

    code: str
    name: str
    dept_code: str
    is_default: int
    is_active: int


class AccountNode(TypedDict):
    """科目树节点。children 已由后端组装好。"""

    code: str
    name: str
    parent_code: str | None
    level: int
    is_leaf: int
    is_active: int
    sort: int
    children: list[AccountNode]


class VoucherLine(TypedDict):
    id: int
    voucher_id: int
    seq: int
    account_code: str
    cost_center: str
    debit_cents: int
    summary: str


class VoucherError(TypedDict):
    """校验错误。field 是 lines[0].account_code 这种路径。"""

    field: str
    code: str
    message: str


class Voucher(TypedDict):
    """凭证表头。状态：draft / pending / submitted / voided。"""

    id: int
    voucher_no: str | None
    external_ref: str
    voucher_date: str
    summary: str
    dept_code: str
    attachment_count: int
    status: str
    created_by: str
    created_at: str
    saved_at: str | None
    submitted_at: str | None
    submitted_by: str | None
    approved_at: str | None
    approved_by: str | None
    review_note: str | None


class VoucherDetail(Voucher):
    """详情：表头 + 明细 + 错误 + 两个派生字段。"""

    lines: list[VoucherLine]
    errors: list[VoucherError]
    validated: bool
    total_cents: int


class VoucherLineInput(TypedDict):
    """写入明细的形状。没有 id / seq，seq 由数组顺序生成。"""

    account_code: str
    cost_center: str
    debit_cents: int
    summary: str


class VoucherInput(TypedDict):
    """建单 / 保存整张单据的形状。"""

    external_ref: str
    voucher_date: str
    summary: str
    dept_code: str
    attachment_count: int
    lines: list[VoucherLineInput]


class CreateResult(TypedDict):
    """POST /api/vouchers 的返回。ok=False 时 errors 非空。"""

    id: int
    ok: bool
    errors: list[VoucherError]


class VoucherPage(TypedDict):
    """列表分页结果。"""

    total: int
    page: int
    page_size: int
    items: list[Voucher]


class SaveResult(TypedDict):
    """PUT /api/vouchers/{id} 的返回。"""

    ok: bool
    errors: list[VoucherError]
