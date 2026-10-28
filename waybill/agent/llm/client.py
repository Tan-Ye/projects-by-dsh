"""通用 LLM 客户端（OpenAI 兼容协议）。

职责边界：

    只负责  发消息、拿回复、翻译错误、记录用量
    不负责  拼 prompt、解析业务 JSON、写数据库

这样换模型/换供应商只改这一个文件；prompt 改了不碰传输层。
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Any, TypedDict, Literal

import httpx

import config

# ---------------------------------------------------------------------------
# 协议类型
# ---------------------------------------------------------------------------

class Message(TypedDict):
    """一条对话消息。role 只有 system / user / assistant。"""
    role: Literal["system", "user", "assistant"]
    content: str

class Usage(TypedDict):
    """token 用量。审计里 runs.cost 就是靠它算的。"""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class ChatResult(TypedDict):
    """一次补全的结果。"""

    content: str
    model: str          # 实际使用的模型，可能和请求的不同
    usage: Usage
    finish_reason: str  # stop / length / content_filter

# ---------------------------------------------------------------------------
# 错误
# ---------------------------------------------------------------------------

class LlmError(Exception):
    """一次调用失败。

    retryable 决定上层要不要重试：
      网络抖动、限流、对方 5xx → 可以
      key 不对、参数非法       → 重试一百次也一样
    """

    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


# ---------------------------------------------------------------------------
# 客户端
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0)
USAGE_LOG = config.AGENT_DIR / "logs" / "llm.jsonl"

def _backoff_seconds(attempt: int) -> float:
    """第 n 次重试前等多久：1s、2s，外加随机抖动。

    抖动是为了避免多个任务同时重试，二次打垮对方。
    """
    return 2 ** (attempt - 1) + random.uniform(0.0, 0.5)

def _error_from_response(response: httpx.Response) -> LlmError:
    """把 HTTP 状态码翻成"能重试" / "不能重试"。"""
    try:
        detail = response.json().get("error", {}).get("message", "")
    except ValueError:
        detail = response.text[:200]
    
    status = response.status_code
    if status in (401, 403):
        return LlmError("AUTH", f"鉴权失败 ({status}): {detail}", retryable=False)
    if status == 429:
        return LlmError("RATE_LIMIT", f"限流 (429) : {detail}", retryable=True)
    if status >= 500:
        return LlmError("SERVER", f"服务器错误 ({status}) : {detail}", retryable=True)
    return LlmError("BAD_REQUEST", f"请求被拒（{status}）：{detail}", retryable=False)

class LlmClient:
    def __init__(self, *, base_url: str, api_key: str, model: str, max_retries: int = 2,  timeout: httpx.Timeout | None = None)  -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout or DEFAULT_TIMEOUT,
        )
        self._api_key = api_key
        self._model = model
        self._max_retries = max_retries

    @property
    def model(self) -> str:
        """模型名。留痕要用——审计里得知道是谁给的建议。"""
        return self._model

    @classmethod
    def from_config(cls) -> LlmClient:
        """按 config 里的环境变量建一个。缺 key 会立刻抛错。"""
        return cls(
            base_url = config.LLM_BASE_URL,
            api_key = config.require_llm_key(),
            model = config.LLM_MODEL,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    # ---- 对外 ------------------------------------------------------- #

    async def chat(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 512,
        json_mode: bool = False,
    ) -> ChatResult:
        """
        发一次补全请求。

        temperature 默认 0：分类要可复现，同样输入必须得到同样结果，
        否则审计里"为什么这次选了这个科目"说不清楚。
        """
        payload : dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = { "type": "json_object" }
        
        attempt = 0
        while True:
            started = time.perf_counter()
            try:
                result = await self._post(payload)
            except LlmError as exc:
                if not exc.retryable or attempt >= self._max_retries:
                    raise
                attempt += 1
                await asyncio.sleep(_backoff_seconds(attempt))
                continue
            self._record_usage(result, ((time.perf_counter() - started) * 1000))
            return result

    # ---- 内部 ------------------------------------------------------- #

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
        }
    
    async def _post(self, payload: dict[str, Any]) -> ChatResult:
        try:
            response = await self._client.post("/chat/completions", json=payload, headers=self._headers())
        except httpx.TimeoutException as exc:
            raise LlmError("TIMEOUT", f"请求超时: {exc}", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise LlmError("NETWORK", f"网络错误: {exc}", retryable=True) from exc
            
        if response.status_code >= 400:
            raise _error_from_response(response=response)
        
        return self._parse(response)

    def _parse(self, response: httpx.Response) -> ChatResult:
        """解析响应。结构不对就是不对，不猜、不修补。"""
        try: 
            data = response.json()
        except ValueError as exc:
            raise LlmError("BAD_RESPONSE", "响应不是 JSON", retryable=False) from exc
        
        choices = data.get("choices") or []
        if not choices:
            raise LlmError("BAD_RESPONSE", "响应没有 choices", retryable=False)
        
        choice = choices[0]
        usage = data.get("usage") or {}

        return ChatResult(
            content=choice.get("message", {}).get("content", ""),
            model = data.get("model", self._model),
            usage = Usage(
                prompt_tokens=int(usage.get("prompt_tokens", 0)),
                completion_tokens=int(usage.get("completion_tokens", 0)),
                total_tokens=int(usage.get("total_tokens", 0)),
            ),
            finish_reason=choice.get("finish_reason", "unknown"),
        )

    
    def _record_usage(self, result: ChatResult, latency_ms: float) -> None:
        """往 logs/llm.jsonl 追加一行。

        日志失败不能影响主流程——记账丢了可以补，请求失败用户就得等。
        只记 token 和模型，不记 prompt 全文，避免业务数据进日志。
        """
        line = {
            "model": result["model"],
            "prompt_tokens": result["usage"]["prompt_tokens"],
            "completion_tokens": result["usage"]["completion_tokens"],
            "latency_ms": round(latency_ms, 1),
            "finish_reason": result["finish_reason"],
        }
        try:
            USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
            with USAGE_LOG.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(line, ensure_ascii=False) + "\n")
        except OSError:
            pass
