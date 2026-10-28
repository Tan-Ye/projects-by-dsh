"""把"定位失败"接成自愈：抓快照 → 问模型 → 改步骤。

这里只负责编排，不负责提示词（那是 llm/locate.py）也不负责重试（那是 replay）。
"""

from __future__ import annotations

import copy
import json

from browser.replay import RepairDecision, RepairHook, StepFailed
from browser.snapshot import snapshot_page
from llm import LlmClient
from llm.client import LlmError
from llm.locate import LocateError, suggest_target


def _apply_target(step: dict[str, object], where: str | None, new_target: dict[str, str]) -> dict[str, object]:
    """把新 target 写进步骤的对应位置。"""
    fixed = copy.deepcopy(step)

    if where is None or where == "action.target":
        fixed["target"] = new_target
        return fixed

    if where.startswith("asserts[") and where.endswith("].target"):
        index = int(where[len("asserts[") : -len("].target")])
        asserts = fixed.get("asserts")
        if not isinstance(asserts, list) or index >= len(asserts):
            raise StepFailed("REPAIR_UNSUPPORTED_PATH", f"断言 {where} 不存在")
        spec = asserts[index]
        if not isinstance(spec, dict):
            raise StepFailed("REPAIR_UNSUPPORTED_PATH", f"断言 {where} 不是对象")
        spec["target"] = new_target
        return fixed

    raise StepFailed("REPAIR_UNSUPPORTED_PATH", f"不知道该把新定位写到 {where}")


def make_repairer(client: LlmClient) -> RepairHook:
    """构造一个自愈钩子。模型只给建议，能不能用由 replay 重试决定。"""

    async def repair(page, step: dict[str, object], failure: StepFailed) -> RepairDecision | None:
        print(f"  [自愈] 第 {step['seq']} 步 [{failure.code}] where={failure.where}")

        snapshot = await snapshot_page(page)
        try:
            suggestion = await suggest_target(
                client,
                intent=str(step["intent"]),
                failure_code=failure.code,
                failure_message=failure.message,
                old_target=step.get("target"),  # type: ignore[arg-type]
                target_path=failure.where,
                snapshot=snapshot,
            )
        except (LocateError, LlmError) as exc:
            print(f"  [自愈] 模型没给出建议 [{exc.code}] {exc.message}")
            return None

        new_target = {"by": str(suggestion["by"]), "value": str(suggestion["value"])}
        print(
            f"  [自愈] 建议 {new_target['by']}={new_target['value']} "
            f"（置信度 {suggestion['confidence']}，{suggestion['rationale']}）"
        )

        try:
            fixed = _apply_target(step, failure.where, new_target)
        except StepFailed as exc:
            print(f"  [自愈] 写入失败：{exc.message}")
            return None

        return RepairDecision(
            step=fixed,
            confidence=float(suggestion["confidence"]),  # type: ignore[arg-type]
            rationale=str(suggestion["rationale"]),
            model=client.model,
        )

    return repair


def dump_repair(fix: dict[str, object]) -> str:
    """给日志用的一行摘要。"""
    return json.dumps(
        {
            "seq": fix["seq"],
            "old": fix["old_target"],
            "new": fix["new_target"],
            "model": fix["model"],
        },
        ensure_ascii=False,
    )
