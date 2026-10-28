"""跑评测集：重置 → 逐个任务 → 独立核对 → 四个指标。

    python -m scripts.evaluate
    python -m scripts.evaluate --label v2          # 漂移对照，报告里带上标签
    python -m scripts.evaluate --only T3           # 只跑一个

判定原则（docs/02-tasks.md）：**看财务系统终态，不看 agent 自述**。
agent 说成功不算数，checker 只认 /api/state/{external_ref}。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field

import httpx
from playwright.async_api import Page

import config
import store
from browser.session import default_credentials, open_session
from flows.execute import execute_task

TASKS_DIR = config.AGENT_DIR / "tasks"


@dataclass
class Case:
    id: str
    name: str
    recipe: str
    inputs: dict[str, str]
    expect: dict[str, object]
    fixture: str | None = None


@dataclass
class Outcome:
    case: Case
    status: str                       # 任务终态
    reason_code: str | None
    message: str
    voucher: dict[str, object] | None  # /api/state 的结果
    problems: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.problems


def load_cases(only: str | None) -> list[Case]:
    cases: list[Case] = []
    for path in sorted(TASKS_DIR.glob("t[1-5].json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        case = Case(
            id=str(data.get("id", path.stem)),
            name=str(data["name"]),
            recipe=str(data["recipe"]),
            inputs=dict(data.get("inputs", {})),
            expect=dict(data.get("expect", {})),
            fixture=data.get("fixture"),
        )
        if only and case.id.upper() != only.upper():
            continue
        cases.append(case)
    return cases


async def reset_finance(fixture: str | None) -> dict[str, object]:
    """调评测旁路接口，把财务库恢复到任务起点。"""
    async with httpx.AsyncClient(base_url=config.FIN_BASE_URL, timeout=30.0) as client:
        resp = await client.post(
            "/api/_reset",
            json={"fixture": fixture},
            headers={"X-Admin-Token": config.FIN_ADMIN_TOKEN},
        )
        resp.raise_for_status()
        return dict(resp.json())


async def read_state(external_ref: str) -> dict[str, object] | None:
    """独立核对：直接读财务系统，不信 agent 的结论。"""
    async with httpx.AsyncClient(base_url=config.FIN_BASE_URL, timeout=30.0) as client:
        resp = await client.get(f"/api/state/{external_ref}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return dict(resp.json())


def check(case: Case, outcome: Outcome) -> list[str]:
    """按夹具的期望逐条核对，返回问题列表（空表示通过）。"""
    problems: list[str] = []
    expect = case.expect

    expected_status = expect.get("status")
    if expected_status and outcome.status != expected_status:
        problems.append(
            f"任务终态 {outcome.status} ≠ 期望 {expected_status}"
        )

    expected_reason = expect.get("reason_code")
    if expected_reason and outcome.reason_code != expected_reason:
        problems.append(
            f"原因码 {outcome.reason_code or '-'} ≠ 期望 {expected_reason}"
        )

    expected_voucher = expect.get("voucher")
    if isinstance(expected_voucher, dict):
        voucher = outcome.voucher
        wants_exists = expected_voucher.get("exists", True)

        if not wants_exists:
            if voucher is not None:
                problems.append(f"期望没有凭证，实际存在 id={voucher.get('id')}")
            return problems

        if voucher is None:
            problems.append("期望有凭证，财务侧查不到")
            return problems

        for field_name, expected in expected_voucher.items():
            if field_name == "exists":
                continue
            if field_name == "total_yuan":
                actual_cents = voucher.get("total_cents")
                if actual_cents != round(float(str(expected)) * 100):
                    problems.append(
                        f"合计 {actual_cents} 分 ≠ 期望 {expected} 元"
                    )
                continue
            if field_name == "lines":
                lines = voucher.get("lines")
                actual_lines = len(lines) if isinstance(lines, list) else -1
                if actual_lines != expected:
                    problems.append(f"明细行数 {actual_lines} ≠ 期望 {expected}")
                continue
            actual = voucher.get(field_name)
            if actual != expected:
                problems.append(f"{field_name} {actual} ≠ 期望 {expected}")

    return problems


async def run_case(conn, case: Case, page: Page) -> Outcome:
    print(f"\n=== {case.id} {case.name} ===")
    await reset_finance(case.fixture)

    status, message = await execute_task(
        conn,
        task_id=None,
        task_name=case.name,
        recipe_name=case.recipe,
        inputs=case.inputs,
        page=page,
    )

    external_ref = case.inputs.get("doc_no", "")
    voucher = await read_state(external_ref)

    row = conn.execute(
        "SELECT reason_code FROM runs WHERE task_name = ? ORDER BY id DESC LIMIT 1",
        (case.name,),
    ).fetchone()
    reason_code = str(row["reason_code"]) if row and row["reason_code"] else None

    outcome = Outcome(
        case=case,
        status=status,
        reason_code=reason_code,
        message=message,
        voucher=voucher,
    )
    outcome.problems = check(case, outcome)
    return outcome


def metrics(outcomes: list[Outcome]) -> dict[str, float]:
    should_pass = [o for o in outcomes if o.case.expect.get("status") == "succeeded"]
    should_stop = [o for o in outcomes if o.case.expect.get("status") == "waiting_human"]

    def rate(hit: int, total: int) -> float:
        return round(hit / total * 100, 1) if total else 0.0

    return {
        "执行成功率": rate(
            sum(1 for o in should_pass if o.passed), len(should_pass)
        ),
        "拦截准确率": rate(
            sum(1 for o in should_stop if o.passed), len(should_stop)
        ),
        "误拦率": rate(
            sum(1 for o in should_pass if o.status == "waiting_human"), len(should_pass)
        ),
        "误放率": rate(
            sum(1 for o in should_stop if o.status == "succeeded"), len(should_stop)
        ),
    }


def render(outcomes: list[Outcome], label: str) -> str:
    lines = [f"## 评测结果（{label}）", ""]
    lines.append("| 用例 | 任务终态 | 原因码 | 结果 | 说明 |")
    lines.append("|---|---|---|---|---|")

    for outcome in outcomes:
        verdict = "通过" if outcome.passed else "失败"
        detail = "；".join(outcome.problems) if outcome.problems else "-"
        lines.append(
            f"| {outcome.case.id} | {outcome.status} | "
            f"{outcome.reason_code or '-'} | {verdict} | {detail} |"
        )

    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("|---|---|")
    for name, value in metrics(outcomes).items():
        lines.append(f"| {name} | {value}% |")
    return "\n".join(lines)


async def main(label: str, only: str | None) -> int:
    cases = load_cases(only)
    if not cases:
        print("没有可跑的用例")
        return 2

    store.init_db()
    conn = store.connect()
    session = await open_session(*default_credentials())
    try:
        # 整个评测共用一个会话：登录一次，跑完所有用例
        outcomes = [await run_case(conn, case, await session.require_page()) for case in cases]

        # 结果进库，控制台才有得看；markdown 仍然写一份，方便 git diff
        eval_id = store.save_eval(
            conn,
            label=label,
            total=len(outcomes),
            passed=sum(1 for outcome in outcomes if outcome.passed),
            metrics=metrics(outcomes),
            cases=[
                {
                    "id": outcome.case.id,
                    "name": outcome.case.name,
                    "status": outcome.status,
                    "reason_code": outcome.reason_code,
                    "passed": outcome.passed,
                    "problems": outcome.problems,
                }
                for outcome in outcomes
            ],
            created_by="cli",
        )
    finally:
        await session.close()
        conn.close()

    report = render(outcomes, label)
    print("\n" + report)

    report_path = config.AGENT_DIR / "logs" / f"eval-{label}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report + "\n", encoding="utf-8")
    print(f"\n报告已写入 {report_path}（评测 id={eval_id}）")
    return 0 if all(outcome.passed for outcome in outcomes) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="local", help="报告标签，漂移对照用它区分")
    parser.add_argument("--only", default=None, help="只跑某个用例，如 T3")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.label, args.only)))
