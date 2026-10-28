"""科目分类：让模型在**给定候选集**里挑一个。

为什么不让模型自由发挥：
    财务只接受末级科目，模型编一个不存在的编码，后面所有链路都白做。
    所以候选集由代码提供，模型只能选，不能造。

为什么解析失败要硬报错：
    模型在 JSON 外面套一段解释是常事。用正则去抠等于给错误兜底，
    兜出来的结果没人能保证对不对——财务场景宁可失败。
"""

from __future__ import annotations

import json
from typing import TypedDict

from .client import LlmClient, Message

# ---------------------------------------------------------------------------
# 类型
# ---------------------------------------------------------------------------

class AccountOption(TypedDict):
    """候选科目。只放末级科目。"""

    code: str
    name: str

class Alternative(TypedDict):
    """第二候选。审计里要展示"另一个可能是什么"。"""

    code: str
    confidence: float

class Judgment(TypedDict):
    """一次分类的结论。

    chosen 为 None 表示模型也说不准——这是合法结果，不是错误。
    """

    chosen: str | None
    confidence: float
    rationale: str
    alternatives: list[Alternative]

class ClassifyError(Exception):
    """模型返回的东西不能用。和传输层的 LlmError 分开。"""

    def __init__(self,code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """你是财务科目分类助手。

规则：
1. 只能从用户给出的候选科目里选，绝对不得编造编码。
2. 拿不准就把 chosen 设为 null，不要硬猜。
3. 只输出 JSON，不要任何解释性文字，不要 markdown 代码块。"""

OUTPUT_SHAPE = """{
  "chosen": "候选里的科目编码，或 null",
  "confidence": 0 到 1 之间的小数,
  "rationale": "一句话说明理由",
  "alternatives": [{"code": "第二候选编码", "confidence": 0 到 1 之间的小数}]
}"""

def build_user_prompt(summary: str, candidates: list[AccountOption]) -> str:
    """把摘要和候选拼成 prompt。

    纯函数，可以单独测：给定输入，断言输出里包含了什么。
    """
    lines = "\n".join(f"- {item['code']} {item['name']}" for item in candidates)
    return (
        f"费用说明：{summary}\n\n"
        f"候选科目（只能从这里选）：\n{lines}\n\n"
        f"输出 JSON，格式：\n{OUTPUT_SHAPE}"
    )

# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------

def parse_judgment(content: str, candidates: list[AccountOption]) -> Judgment:
    """把模型输出解析成 Judgment。任何不合规都抛 ClassifyError。"""
    try:
        data = json.loads(content)
    except ValueError as exc:
        raise ClassifyError("BAD_JSON", f"输出不是 JSON：{content[:120]!r}") from exc
    
    if not isinstance(data, dict):
        raise ClassifyError("BAD_JSON", "输出不是 JSON 对象")
    
    codes = {item["code"] for item in candidates}
    chosen = data.get("chosen")

    if chosen is not None:
        if not isinstance(chosen, str):
            raise ClassifyError("BAD_CHOSEN", f"chosen 不是字符串：{chosen!r}")
        if chosen not in codes:
            raise ClassifyError("UNKNOWN_ACCOUNT", f"模型选了不在候选里的科目：{chosen}")

    confidence = data.get("confidence", 0.0)
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <=1:
        raise ClassifyError("BAD_CONFIDENCE", f"confidence 不是 0-1 的数：{confidence!r}")
    
    rationale = data.get("rationale", "")
    if not isinstance(rationale, str):
        raise ClassifyError("BAD_RATIONALE", "rationale 不是字符串")
    
    alternatives: list[Alternative] = []
    for item in data.get("alternatives") or []:
        if not isinstance(item, dict):
            continue
        code = item.get("code")
        alt_confidence = item.get("confidence", 0.0)
        # 只收候选集里真实存在的；模型编的丢弃，不让它污染审计
        if code in codes and isinstance(alt_confidence, (int, float)):
            alternatives.append(Alternative(code=code, confidence=float(alt_confidence)))

    return Judgment(
        chosen=chosen,
        confidence=confidence,
        rationale=rationale,
        alternatives=alternatives,
    )

# ---------------------------------------------------------------------------
# 对外
# ---------------------------------------------------------------------------

async def classify_account(
    client: LlmClient,
    summary: str,
    candidates: list[AccountOption],
) -> Judgment:
    """让模型在候选里挑一个科目。

    client 由调用方传入，不是在这里 new——这样测试可以塞假客户端，
    也避免每次分类都新建一个连接池。
    """
    if not candidates:
        raise ClassifyError("NO_CANDIDATES", "没有候选科目可分类")
    
    messages: list[Message] = [
        Message(role="system", content=SYSTEM_PROMPT),
        Message(role="user", content=build_user_prompt(summary, candidates)),
    ]

    result = await client.chat(messages, json_mode=True, max_tokens=300)

    if result["finish_reason"] == "length":
        # 被截断的输出一定是半截 JSON，解析了也是错的，提前说清楚
        raise ClassifyError("TRUNCATED", "输出被截断，请调大 max_tokens")

    return parse_judgment(result["content"], candidates)