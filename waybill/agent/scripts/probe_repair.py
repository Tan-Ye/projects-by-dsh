"""验证自愈的控制流和真模型修复。

    python -m scripts.probe_repair           # 假修复器，能修好
    python -m scripts.probe_repair --giveup  # 假修复器返回 None
    python -m scripts.probe_repair --wrong   # 假修复器给错答案
    python -m scripts.probe_repair --real    # 真模型：快照 → 建议 → 重试

前三种证明控制流；--real 证明模型能看懂快照。
"""

from __future__ import annotations

import argparse
import asyncio
import json

from browser.repair import make_repairer
from browser.replay import RepairDecision, RepairHook, StepFailed, load_recipe, render, replay
from browser.session import default_credentials, open_session
from browser.snapshot import snapshot_page
from llm import LlmClient


def fixed_step(step: dict[str, object], value: str) -> dict[str, object]:
    """复制一份步骤并换掉 target，假修复器用。"""
    fixed = json.loads(json.dumps(step))
    fixed["target"]["value"] = value
    return fixed


def make_fake(mode: str) -> RepairHook:
    async def repair(page, step, failure: StepFailed) -> RepairDecision | None:
        print(f"  [假修复] 第 {step['seq']} 步失败 [{failure.code}] where={failure.where}")
        preview = (await snapshot_page(page)).splitlines()[:4]
        print("  [假修复] 页面摘要：\n    " + "\n    ".join(preview))

        if mode == "giveup":
            print("  [假修复] 放弃")
            return None
        if mode == "wrong":
            return RepairDecision(
                step=fixed_step(step, "table.not-exist"),
                confidence=0.9,
                rationale="故意给错",
                model="fake",
            )
        return RepairDecision(
            step=fixed_step(step, "table.grid"),
            confidence=0.99,
            rationale="假修复器兜底",
            model="fake",
        )

    return repair


async def main(mode: str) -> int:
    recipe = load_recipe("oa_read_doc_broken")
    steps = render(recipe["steps"], {"doc_no": "BX-2024-0912"})

    client: LlmClient | None = None
    if mode == "real":
        client = LlmClient.from_config()
        hook: RepairHook = make_repairer(client)
    else:
        hook = make_fake(mode)

    session = await open_session(*default_credentials())
    try:
        run = await replay(recipe, steps, repair=hook, page=await session.require_page())
    finally:
        await session.close()
        if client is not None:
            await client.aclose()

    print("\n结果:")
    print("  ok        :", run["ok"])
    print("  步骤数    :", len(run["steps"]))
    print("  自愈次数  :", len(run["fixes"]))
    for fix in run["fixes"]:
        print(
            f"  - 第 {fix['seq']} 步 {fix['old_target']} → {fix['new_target']}"
            f"（{fix['confidence']}，{fix['rationale']}）"
        )
    if not run["ok"]:
        print("  失败步骤  :", run["failed_step"])
        print("  失败位置  :", run["failed_where"])
        print("  原因码    :", run["reason_code"])
    else:
        print("  明细行数  :", len(run["outputs"].get("lines", [])))  # type: ignore[arg-type]
    return 0 if run["ok"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--giveup", action="store_true")
    parser.add_argument("--wrong", action="store_true")
    parser.add_argument("--real", action="store_true")
    args = parser.parse_args()

    if args.giveup:
        flag = "giveup"
    elif args.wrong:
        flag = "wrong"
    elif args.real:
        flag = "real"
    else:
        flag = "fix"
    raise SystemExit(asyncio.run(main(flag)))
