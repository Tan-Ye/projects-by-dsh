"""OA 数据 → 财务凭证字段（纯函数）。

不碰网络、不碰浏览器：给数据，返回数据。
流程编排（登录、取元数据、建单、修正、核验）在 scripts/run_task.py。

财务 API 的类型在 fin/models.py，那是它们的来源，这里只导入使用。
"""

from __future__ import annotations

import re

from fin.models import AccountNode, Department, VoucherInput, VoucherLineInput

from .parse import parse_count, parse_yuan

# 明细行的键来自页面表头，跑起来才知道叫什么——这里只能是 str → str
OaDetailRow = dict[str, str]

# 规则映射：费用说明里的关键词 → 科目
# 顺序有意义：先匹配到的赢。"打车" 和 "招待" 同时出现时看谁在前。
ACCOUNT_RULES: list[tuple[str, str]] = [
    (r"打车|出租|滴滴|网约车|机场大巴", "6601.03"),
    (r"住宿|酒店|宾馆", "6601.01"),
    (r"招待|宴请|餐费", "6601.04"),
    (r"办公用品|文具|打印纸", "6601.05.01"),
    (r"快递|邮寄|顺丰", "6601.05.02"),
]


def classify_account(summary: str) -> tuple[str | None, str]:
    """费用说明 → (科目编码, 命中的规则)。

    返回 None 表示规则覆盖不到——这种才需要 LLM 或人工判断。
    把"没匹配上"显式表达出来，比默默塞一个默认科目安全得多。
    """
    for pattern, code in ACCOUNT_RULES:
        if re.search(pattern, summary):
            return code, pattern
    return None, ""


def match_department(name: str, departments: list[Department]) -> str | None:
    """部门名 → 部门编码。精确匹配，匹配不上返回 None。"""
    for item in departments:
        if item["name"] == name:
            return item["code"]
    return None


def flatten_leaf_accounts(nodes: list[AccountNode]) -> set[str]:
    """科目树 → 末级科目编码集合。

    财务只接受末级科目，用它做最后一道校验。
    """
    codes: set[str] = set()
    for node in nodes:
        if node["is_leaf"]:
            codes.add(node["code"])
        else:
            codes |= flatten_leaf_accounts(node["children"])
    return codes


def build_voucher(
    *,
    doc_no: str,
    voucher_date: str,
    reason: str,
    attachment_count: int,
    dept_code: str,
    cost_center: str,
    rows: list[OaDetailRow],
    leaf_accounts: set[str],
    account_overrides: dict[str, str] | None = None,
) -> tuple[VoucherInput, list[str]]:
    """明细行 → 财务凭证的 payload。

    account_overrides：摘要 → 科目编码，来自预分类阶段（LLM）。
    规则命中时不看它；规则没命中时才用。这样规则永远优先，
    确定的部分不花钱、也不受模型波动影响。

    返回 (payload, 问题列表)。问题列表不为空时不要提交——
    它是给人和后续判断用的。
    """
    lines: list[VoucherLineInput] = []
    problems: list[str] = []

    for index, row in enumerate(rows, start=1):
        summary = row.get("费用说明", "")
        code, _matched = classify_account(summary)

        # 规则没命中，但预分类阶段给了判断
        if code is None and account_overrides:
            code = account_overrides.get(summary)

        if code is None:
            problems.append(f"第 {index} 行 {summary} 匹配不到科目")
            continue
        if code not in leaf_accounts:
            problems.append(f"第 {index} 行科目 {code} 不是末级，财务会拒收")
            continue

        lines.append(
            {
                "account_code": code,
                "cost_center": cost_center,
                "debit_cents": parse_yuan(row.get("金额", "")),
                "summary": summary,
            }
        )

    payload: VoucherInput = {
        "external_ref": doc_no,
        "voucher_date": voucher_date,
        "summary": reason,
        "dept_code": dept_code,
        "attachment_count": attachment_count,
        "lines": lines,
    }
    return payload, problems


def first_line_date(lines: list[OaDetailRow]) -> str:
    """取明细里第一个非空的「发生日期」。"""
    for row in lines:
        value = row.get("发生日期", "").strip()
        if value:
            return value
    return ""


def build_from_document(
    *,
    doc: dict[str, str],
    lines: list[OaDetailRow],
    departments: list[Department],
    cost_center: str,
    leaf_accounts: set[str],
    account_overrides: dict[str, str] | None = None,
) -> tuple[VoucherInput | None, list[str]]:
    """OA 单据（表头 + 明细）→ 财务 payload。

    返回 (payload, 问题)。payload 为 None 表示连表头都凑不齐——
    这种连提交都不用试，直接转人工。
    """
    problems: list[str] = []

    doc_no = doc.get("单号", "").strip()
    if not doc_no:
        problems.append("单据头里没有「单号」")

    department = doc.get("部门", "").strip()
    dept_code = match_department(department, departments)
    if dept_code is None:
        problems.append(f"部门「{department}」在财务系统里不存在")

    voucher_date = first_line_date(lines) or doc.get("提交时间", "")[:10]
    if not voucher_date:
        problems.append("拿不到凭证日期：明细没有发生日期，单据也没有提交时间")

    if problems:
        return None, problems

    return build_voucher(
        doc_no=doc_no,
        voucher_date=voucher_date,
        reason=doc.get("事由", "").strip(),
        attachment_count=parse_count(doc.get("附单据数", "")),
        dept_code=dept_code or "",
        cost_center=cost_center,
        rows=lines,
        leaf_accounts=leaf_accounts,
        account_overrides=account_overrides,
    )
