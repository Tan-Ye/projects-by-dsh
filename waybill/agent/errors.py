"""统一的错误格式。

所有"需要停下来说明原因"的地方都抛 AgentError：

    code     机器读：落库、统计、决定任务状态
    message  人读：日志、控制台
    detail   结构化补充：缺哪个字段、哪一行、期望与实际

为什么用异常而不是返回值：
    返回值会被沿途忽略，异常不会。一个"没处理"的错误就是崩溃，
    而不是静默地继续往前跑。
"""

from __future__ import annotations

from typing import Any


class AgentError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"
