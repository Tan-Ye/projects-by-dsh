"""预分类：规则覆盖不到的摘要交给模型。

规则优先的理由：确定性 + 零成本。调用模型是兜底，不是主路径。
"""

from __future__ import annotations

import sqlite3

import store
from business.classify_policy import decide
from business.mapping import classify_account as rule_classify
from fin.models import AccountNode
from llm import AccountOption, ClassifyError, LlmClient, classify_account
from llm.client import LlmError


def leaf_options(nodes: list[AccountNode]) -> list[AccountOption]:
    """科目树 → 模型候选列表（只要末级，父科目不能选）。"""
    options: list[AccountOption] = []
    for node in nodes:
        if node["is_leaf"]:
            options.append({"code": node["code"], "name": node["name"]})
        else:
            options.extend(leaf_options(node["children"]))
    return options


async def preclassify(
    lines: list[dict[str, str]],
    options: list[AccountOption],
    conn: sqlite3.Connection,
    run_id: int,
) -> tuple[dict[str, str], list[str]]:
    """对规则覆盖不到的摘要逐条问模型。

    返回 (可采信的科目覆盖表, 判不清的问题列表)。
    每次判断都写进 judgments 表——它是审计里"为什么选这个科目"的唯一依据。
    """
    pending = sorted(
        {
            row.get("费用说明", "")
            for row in lines
            if row.get("费用说明", "") and rule_classify(row["费用说明"])[0] is None
        }
    )
    if not pending:
        return {}, []

    overrides: dict[str, str] = {}
    problems: list[str] = []

    client = LlmClient.from_config()
    try:
        for summary in pending:
            try:
                judgment = await classify_account(client, summary, options)
            except (ClassifyError, LlmError) as exc:
                store.add_judgment(
                    conn,
                    run_id,
                    summary=summary,
                    chosen=None,
                    confidence=None,
                    rationale="",
                    accepted=False,
                    reason=f"{exc.code}: {exc.message}",
                )
                problems.append(f"「{summary}」分类失败 [{exc.code}] {exc.message}")
                continue

            decision = decide(judgment["chosen"], judgment["confidence"])
            store.add_judgment(
                conn,
                run_id,
                summary=summary,
                chosen=judgment["chosen"],
                confidence=judgment["confidence"],
                rationale=judgment["rationale"],
                accepted=decision["accepted"],
                reason=decision["reason"],
            )

            if not decision["accepted"] or decision["code"] is None:
                problems.append(f"「{summary}」{decision['reason']}")
                continue

            overrides[summary] = decision["code"]
            print(
                f"模型分类: {summary} → {decision['code']}"
                f"（{judgment['rationale']}，置信度 {judgment['confidence']:.2f}）"
            )
    finally:
        await client.aclose()

    return overrides, problems
