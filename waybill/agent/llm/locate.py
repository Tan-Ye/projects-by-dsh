"""定位修复：让模型在页面快照里找出正确的 target。

和 llm/classify.py 一个路数：这里只负责"拼 prompt + 解析 + 校验"，
真正抓快照、改步骤、重试在 browser/repair.py。
"""

from __future__ import annotations

import json

from llm.client import ChatResult, LlmClient

# 只允许这几种定位方式：配方里的 locate() 认识哪些，这里就给哪些
SUPPORTED_BY = frozenset({"css", "name", "text", "role"})

SYSTEM_PROMPT = (
    "你是网页自动化的定位修复助手。配方里某个元素的定位方式失效了，"
    "你要根据当前页面的元素清单，给出一个新的定位方式。\n"
    "规则：\n"
    "1. 只能从页面清单里真实存在的元素里选，不能编造。\n"
    "2. by 只能是 css / name / text / role。\n"
    "3. 优先选稳定的特征：id、name、语义化的 class；避免依赖顺序和临时样式。\n"
    "4. 拿不准就返回 null，不要猜。\n"
    "只输出 JSON。"
)

OUTPUT_SHAPE = """{
  "by": "css | name | text | role",
  "value": "定位表达式",
  "confidence": 0.0,
  "rationale": "为什么选它，30 字以内"
}"""


class LocateError(Exception):
    """修复建议不可用。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def build_user_prompt(
    *,
    intent: str,
    failure_code: str,
    failure_message: str,
    old_target: dict[str, str] | None,
    target_path: str | None,
    snapshot: str,
) -> str:
    old = f"{old_target['by']}={old_target['value']}" if old_target else "(无)"
    return (
        f"这一步想做的事：{intent}\n"
        f"失败位置：{target_path or 'unknown'}\n"
        f"原来的定位：{old}\n"
        f"失败原因：[{failure_code}] {failure_message}\n\n"
        f"当前页面元素清单（每行一个元素）：\n{snapshot}\n\n"
        f"请给出新的定位方式，格式：\n{OUTPUT_SHAPE}"
    )


def parse_suggestion(content: str) -> dict[str, object]:
    """解析模型的回答。任何不合规的地方都抛 LocateError，不静默兜底。"""
    text = content.strip()
    if text.startswith("```"):
        # 模型有时会套 markdown 代码块
        text = text.strip("`")
        text = text[text.find("{") :]

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LocateError("BAD_JSON", f"模型输出不是 JSON: {content[:120]!r}") from exc

    by = str(data.get("by", "")).strip()
    value = str(data.get("value", "")).strip()

    if by not in SUPPORTED_BY:
        raise LocateError("UNSUPPORTED_BY", f"不支持的定位方式: {by!r}")
    if not value:
        raise LocateError("EMPTY_VALUE", "定位值为空")

    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError) as exc:
        raise LocateError("BAD_CONFIDENCE", "confidence 不是数字") from exc

    return {
        "by": by,
        "value": value,
        "confidence": max(0.0, min(1.0, confidence)),
        "rationale": str(data.get("rationale", "")).strip()[:200],
    }


async def suggest_target(
    client: LlmClient,
    *,
    intent: str,
    failure_code: str,
    failure_message: str,
    old_target: dict[str, str] | None,
    target_path: str | None,
    snapshot: str,
) -> dict[str, object]:
    """问模型要一个新的定位方式。"""
    result: ChatResult = await client.chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_user_prompt(
                    intent=intent,
                    failure_code=failure_code,
                    failure_message=failure_message,
                    old_target=old_target,
                    target_path=target_path,
                    snapshot=snapshot,
                ),
            },
        ],
        temperature=0.0,
        max_tokens=400,
        json_mode=True,
    )

    content = result["content"]
    if result["finish_reason"] == "length":
        raise LocateError("TRUNCATED", "模型输出被截断")

    return parse_suggestion(content)
