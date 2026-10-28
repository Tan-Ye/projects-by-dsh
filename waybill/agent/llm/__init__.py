"""LLM 相关能力。

    client.py   通用补全（传输、重试、错误分类、用量记录）
    classify.py 科目分类（prompt、结构化输出、置信度）

依赖方向：classify → client，反过来不行。
"""

from __future__ import annotations

from .client import ChatResult, LlmClient, LlmError, Message, Usage
from .classify import (
    AccountOption,
    ClassifyError,
    Judgment,
    classify_account,
)


__all__ = ["LlmClient", "LlmError", "Message", "Usage", "ChatResult", "AccountOption", "Judgment", "ClassifyError", "classify_account"]
