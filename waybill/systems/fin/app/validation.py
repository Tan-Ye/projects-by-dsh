"""保存凭证时的校验规则。

返回错误列表，空列表表示通过。每个错误带 `field / code / message`，
field 用 `lines[2].account_code` 这种路径——前端能高亮到具体输入框，
agent 也能据此判断该改哪一处。
"""

from __future__ import annotations

import sqlite3

from .db import VoucherErrorRow, VoucherInput, get_account, get_cost_center


def validate(conn: sqlite3.Connection, data: VoucherInput) -> list[VoucherErrorRow]:
    """跑完所有规则，一次性返回全部错误。

    不做"遇到第一个错就返回"：一次给全，调用方改一轮就能通过，
    否则要来回保存好几次。
    """
    errors: list[VoucherErrorRow] = []
    lines = data["lines"]

    if not lines:
        errors.append(_err("lines", "NO_LINES", "至少需要一行明细"))

    if data["attachment_count"] < 1:
        errors.append(_err("attachment_count", "ATTACHMENT_REQUIRED", "附单据数至少为 1"))

    total = 0
    for index, line in enumerate(lines):
        path = f"lines[{index}]"

        if line["debit_cents"] <= 0:
            errors.append(_err(f"{path}.debit_cents", "AMOUNT_INVALID", "金额必须大于 0"))
        total += line["debit_cents"]

        account = get_account(conn, line["account_code"])
        if account is None:
            errors.append(_err(f"{path}.account_code", "ACCOUNT_NOT_FOUND",
                               f"科目 {line['account_code']} 不存在"))
        elif not account["is_active"]:
            errors.append(_err(f"{path}.account_code", "ACCOUNT_INACTIVE",
                               f"科目 {line['account_code']} 已停用"))
        elif not account["is_leaf"]:
            errors.append(_err(f"{path}.account_code", "ACCOUNT_NOT_LEAF",
                               f"科目 {line['account_code']} 不是末级科目"))

        center = get_cost_center(conn, line["cost_center"])
        if center is None:
            errors.append(_err(f"{path}.cost_center", "COST_CENTER_MISMATCH",
                               f"成本中心 {line['cost_center']} 不存在"))
        elif not center["is_active"] or center["dept_code"] != data["dept_code"]:
            errors.append(_err(f"{path}.cost_center", "COST_CENTER_MISMATCH",
                               f"成本中心 {line['cost_center']} 不属于部门 {data['dept_code']}"))

    if lines and total <= 0:
        errors.append(_err("total_cents", "TOTAL_ZERO", "借方合计必须大于 0"))

    return errors


def _err(field: str, code: str, message: str) -> VoucherErrorRow:
    return {"field": field, "code": code, "message": message}
