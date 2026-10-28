"""核验：财务落库的内容是否和 OA 源头一致。

为什么需要它：
    财务的 validated 只说明"格式合法"，不说明"数对"。
    金额填成 100（源头 128.60）也能通过校验——那是错账，不是格式错误。

纯函数：给数据，返回检查结果，不碰网络、不碰数据库。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypedDict

from .parse import parse_count, parse_yuan


class Check(TypedDict):
    """一条核验结论。layer 区分是单据内部一致，还是跨系统一致。"""

    layer: str                   # document / cross_system
    field: str
    passed: bool
    reason_code: str | None
    expected: str
    actual: str


def _check(
    *,
    layer: str,
    field: str,
    passed: bool,
    reason_code: str,
    expected: object,
    actual: object,
) -> Check:
    return Check(
        layer=layer,
        field=field,
        passed=passed,
        reason_code=None if passed else reason_code,
        expected=str(expected),
        actual=str(actual),
    )


def verify_voucher(
    *,
    doc: dict[str, str],
    rows: list[dict[str, str]],
    detail: Mapping[str, object],
    dept_code: str,
) -> list[Check]:
    """逐字段核对"源头 vs 落库"。

    返回全部检查项，包括通过的——只记失败的，就没人能证明"核对过"。
    """
    checks: list[Check] = []

    # 1. 单号：幂等支点，错了一切都错
    expected_ref = doc.get("单号", "").strip()
    checks.append(
        _check(
            layer="cross_system",
            field="external_ref",
            passed=detail.get("external_ref") == expected_ref,
            reason_code="REF_MISMATCH",
            expected=expected_ref,
            actual=detail.get("external_ref"),
        )
    )

    # 2. 金额合计：源头逐行解析求和，对财务的 total_cents
    expected_total = 0
    for row in rows:
        try:
            expected_total += parse_yuan(row.get("金额", ""))
        except ValueError:
            checks.append(
                _check(
                    layer="document",
                    field="amount_sum",
                    passed=False,
                    reason_code="AMOUNT_UNPARSABLE",
                    expected="可解析的金额",
                    actual=row.get("金额"),
                )
            )
            return checks

    checks.append(
        _check(
            layer="cross_system",
            field="total_cents",
            passed=detail.get("total_cents") == expected_total,
            reason_code="AMOUNT_MISMATCH",
            expected=expected_total,
            actual=detail.get("total_cents"),
        )
    )

    # 3. 明细行数：源头几行，落库就该几行
    stored = detail.get("lines")
    stored_count = len(stored) if isinstance(stored, list) else -1
    checks.append(
        _check(
            layer="document",
            field="line_count",
            passed=stored_count == len(rows),
            reason_code="ROW_COUNT_MISMATCH",
            expected=len(rows),
            actual=stored_count,
        )
    )

    # 4. 部门
    checks.append(
        _check(
            layer="cross_system",
            field="dept_code",
            passed=detail.get("dept_code") == dept_code,
            reason_code="DEPT_MISMATCH",
            expected=dept_code,
            actual=detail.get("dept_code"),
        )
    )

    # 5. 附单据数
    expected_atts = parse_count(doc.get("附单据数", ""))
    checks.append(
        _check(
            layer="document",
            field="attachment_count",
            passed=detail.get("attachment_count") == expected_atts,
            reason_code="ATTACHMENT_MISMATCH",
            expected=expected_atts,
            actual=detail.get("attachment_count"),
        )
    )

    return checks
