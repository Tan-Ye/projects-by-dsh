"""把"校验错误"变成"修正动作"。

只处理确定性错误：改完之后不需要人再做判断。
其余一律返回给调用方，由人（或后续的 LLM）决定。
"""

from __future__ import annotations
import re
from fin.models import CostCenter, VoucherError, VoucherInput, VoucherLineInput

# lines[3].cost_center → 3
_LINE_FIELD = re.compile(r"^lines\[(\d+)\]\.(\w+)$")


def line_index(field: str) -> int | None:
    """从字段路径里取出明细行号。不是明细字段就返回 None。"""
    match = _LINE_FIELD.match(field)
    return int(match.group(1)) if match else None


def repair(
    payload: VoucherInput, errors: list[VoucherError], cost_centers: list[CostCenter]
) -> tuple[VoucherInput, list[str]]:
    """做一轮修正，返回 (新 payload, 修不了的问题)。

    只修 COST_CENTER_MISMATCH：部门已定，成本中心换成该部门默认的。
    其他错误原样上报——能自动修的才修，修不了的要让人看见。
    """
    if not cost_centers:
        return payload, ["该部门没有可用的成本中心"]

    default_cost_center = cost_centers[0]["code"]

    lines: list[VoucherLineInput] = [
        {
            "account_code": line["account_code"],
            "cost_center": line["cost_center"],
            "debit_cents": line["debit_cents"],
            "summary": line["summary"],
        }
        for line in payload["lines"]
    ]

    unfixable: list[str] = []

    for error in errors:
        if error["code"] != "COST_CENTER_MISMATCH":
            unfixable.append(f"{error['field']}: {error['message']}")
            continue

        index = line_index(error["field"])
        if index is None or index >= len(lines):
            unfixable.append(f"{error['field']}: 行号对不上，无法修正")
            continue
        lines[index]["cost_center"] = default_cost_center

    repaired: VoucherInput = {
        "external_ref": payload["external_ref"],
        "voucher_date": payload["voucher_date"],
        "summary": payload["summary"],
        "dept_code": payload["dept_code"],
        "attachment_count": payload["attachment_count"],
        "lines": lines,
    }
    return repaired, unfixable
