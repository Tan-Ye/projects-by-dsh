"""一张凭证的完整流程：读证据 → 映射 → 建单 → 核验 → 落库。

不接内存里的产物：证据存进库之后只有一个数据源，
建单和核验都从库里读——这样"读到的"和"用来核对的"保证是同一份。

失败一律抛 AgentError：同一个格式，上层据此决定任务终态。
"""

from __future__ import annotations

import sqlite3

import config
import store
from business.mapping import (
    build_from_document,
    flatten_leaf_accounts,
    match_department,
)
from business.repair import repair
from business.verify import verify_voucher
from errors import AgentError
from fin.client import FinClient
from fin.models import CostCenter, SaveResult, VoucherInput
from flows.classify import leaf_options, preclassify
from reason_codes import (
    ACCOUNT_UNRESOLVED,
    DUPLICATE_DOC,
    EVIDENCE_MISSING,
    MAPPING_MISSING,
    VALIDATION_UNFIXABLE,
    VERIFY_MISMATCH,
)


async def write_to_finance(conn: sqlite3.Connection, run_id: int) -> str:
    """把一次执行的证据写成凭证。成功返回一句结论，需要停下时抛 AgentError。"""
    stored_doc = store.get_extraction(conn, run_id, "doc")
    stored_lines = store.get_extraction(conn, run_id, "lines")
    if not isinstance(stored_doc, dict) or not isinstance(stored_lines, list):
        raise AgentError(EVIDENCE_MISSING, "数据库里没有 doc / lines")

    doc: dict[str, str] = stored_doc
    lines: list[dict[str, str]] = stored_lines

    client = FinClient(config.FIN_BASE_URL)
    try:
        await client.login(config.FIN_USERNAME, config.FIN_PASSWORD)

        departments = await client.departments()
        dept_code = match_department(doc.get("部门", ""), departments)
        if dept_code is None:
            raise AgentError(
                MAPPING_MISSING,
                f"部门「{doc.get('部门')}」在财务系统里不存在",
                detail={
                    "department": doc.get("部门", ""),
                    "choices": [item["name"] for item in departments],
                },
            )

        centers = await client.cost_centers(dept_code)
        if not centers:
            raise AgentError(
                MAPPING_MISSING,
                f"部门 {dept_code} 没有可用的成本中心",
                detail={"dept_code": dept_code},
            )

        accounts = await client.accounts()
        overrides, classify_problems = await preclassify(
            lines, leaf_options(accounts), conn, run_id
        )

        payload, mapping_problems = build_from_document(
            doc=doc,
            lines=lines,
            departments=departments,
            cost_center=centers[0]["code"],
            leaf_accounts=flatten_leaf_accounts(accounts),
            account_overrides=overrides,
        )
        problems = classify_problems + mapping_problems
        if payload is None:
            raise AgentError(
                ACCOUNT_UNRESOLVED,
                "映射不完整，连表头都凑不齐",
                detail={"problems": problems},
            )

        if problems:
            # 判不清：单据照样建，已确定的字段先填进去，剩下的交给人
            voucher_id = await create_draft_only(client, payload)
            raise AgentError(
                ACCOUNT_UNRESOLVED,
                f"草稿 id={voucher_id} 已保存，需人工确认：{'；'.join(problems)}",
                detail={"voucher_id": voucher_id, "problems": problems},
            )

        message, voucher_id = await create_or_update(client, payload, centers)

        # 核验：拿库里的证据比对落库结果
        detail = await client.get_voucher(voucher_id)
        checks = verify_voucher(
            doc=doc, rows=lines, detail=detail, dept_code=dept_code
        )
        store.add_verifications(conn, run_id, list(checks))

        failed = [check for check in checks if not check["passed"]]
        if failed:
            raise AgentError(
                VERIFY_MISMATCH,
                f"落库结果和源头有 {len(failed)} 项不一致",
                detail={
                    "mismatches": [
                        {
                            "field": check["field"],
                            "expected": check["expected"],
                            "actual": check["actual"],
                            "reason_code": check["reason_code"],
                        }
                        for check in failed
                    ]
                },
            )

        return message
    finally:
        await client.aclose()


async def create_draft_only(client: FinClient, payload: VoucherInput) -> int:
    """只建草稿，不修复、不追求校验通过——单据信息该填就填。"""
    existing = await client.find_by_external_ref(payload["external_ref"])
    if existing is not None:
        print(f"单号已存在（幂等命中），复用 id={existing['id']}")
        return existing["id"]

    created = await client.create_voucher(payload)
    print(f"建单（待人工）: id={created['id']} 错误数={len(created['errors'])}")
    for error in created["errors"]:
        print(f"  - [{error['code']}] {error['field']}: {error['message']}")
    return created["id"]


async def create_or_update(
    client: FinClient,
    payload: VoucherInput,
    centers: list[CostCenter],
) -> tuple[str, int]:
    """幂等建单 + 修正循环。返回 (结论, 凭证 id)，修不了抛 AgentError。"""
    existing = await client.find_by_external_ref(payload["external_ref"])
    result: SaveResult | None = None

    if existing is not None:
        voucher_id = existing["id"]
        print(f"单号已存在（幂等命中），复用 id={voucher_id}")

        # 已入账的不能改：这是"需要人决策"，不是"我们出错了"
        if existing["status"] != "draft":
            raise AgentError(
                DUPLICATE_DOC,
                f"单号已存在且状态为 {existing['status']}，不能覆盖",
                detail={"voucher_id": voucher_id, "status": existing["status"]},
            )

        # 草稿可以覆盖：重跑的任务是把它收敛到源头，而不是原样留着
        saved = await client.save_voucher(voucher_id, payload)
        print(f"覆盖已有草稿: ok={saved['ok']} 错误数={len(saved['errors'])}")
        result = saved
    else:
        created = await client.create_voucher(payload)
        voucher_id = created["id"]
        print(f"建单: id={voucher_id} ok={created['ok']} 错误数={len(created['errors'])}")
        result = SaveResult(ok=created["ok"], errors=created["errors"])

    # 修正循环：最多两轮，防止"改了还错、错了再改"无限循环
    attempts = 0
    while not result["ok"] and attempts < 2:
        attempts += 1
        print(f"\n第 {attempts} 轮修正：")
        for error in result["errors"]:
            print(f"  - [{error['code']}] {error['field']}: {error['message']}")

        payload, unfixable = repair(payload, result["errors"], centers)
        if unfixable:
            raise AgentError(
                VALIDATION_UNFIXABLE,
                "校验错误修不了，需要人工处理",
                detail={"unfixable": unfixable, "voucher_id": voucher_id},
            )

        result = await client.save_voucher(voucher_id, payload)
        print(f"  重新保存: ok={result['ok']}")

    detail = await client.get_voucher(voucher_id)
    summary = (
        f"建单: id={detail['id']} status={detail['status']} "
        f"validated={detail['validated']} 合计={detail['total_cents']}分 "
        f"明细={len(detail['lines'])}行"
    )
    return summary, voucher_id
