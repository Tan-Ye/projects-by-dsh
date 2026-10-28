"""分类采信策略——这是业务规则，不是基础设施配置。

所以阈值放这里，不放 config：换一家公司，"多确定才算数"这个数是业务说了算的。
只收原始值（chosen / confidence），不 import llm：
    business 不该依赖传输层，否则单测要拖上 httpx。
"""

from __future__ import annotations

from typing import TypedDict

CONFIDENCE_THRESHOLD = 0.7


class Decision(TypedDict):
    """采信结论。accepted=False 时 reason 说明为什么不采信。"""

    accepted: bool
    code: str | None
    reason: str


def decide(chosen: str | None, confidence: float) -> Decision:
    """判断模型给的结论能不能用。

    三种情况都不采信，但原因不同——原因要能进审计，
    不能只记一句"没过"。
    """
    if chosen is None:
        return Decision(accepted=False, code=None, reason="模型判断为不确定")

    if confidence < CONFIDENCE_THRESHOLD:
        return Decision(
            accepted=False,
            code=None,
            reason=f"置信度 {confidence:.2f} 低于阈值 {CONFIDENCE_THRESHOLD}",
        )

    return Decision(accepted=True, code=chosen, reason="")
