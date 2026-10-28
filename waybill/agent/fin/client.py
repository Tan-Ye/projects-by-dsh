"""财务系统客户端（全异步）。

分层：
    _client    httpx.AsyncClient，只管发请求
    _request   唯一直接调用 _client 的地方：加鉴权头、把 4xx 翻成 FinError
    _get/_post 语义化包装
    login/...  业务方法，只调 _get/_post

契约类型在 fin_models.py，这个文件只放实现。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import httpx

from fin.models import (
    AccountNode,
    CostCenter,
    CreateResult,
    Department,
    SaveResult,
    Voucher,
    VoucherDetail,
    VoucherInput,
    VoucherPage,
)


class FinError(Exception):
    """财务系统返回了 4xx。code 是后端给的错误码。"""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class FinClient:
    def __init__(self, base_url: str) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=10.0)
        self._token: str | None = None

    async def aclose(self) -> None:
        """关掉连接池。必须调用，否则跑几十次任务后进程会卡住。"""
        await self._client.aclose()

    # ---- 底层 ------------------------------------------------------ #

    def _headers(self, auth: bool) -> dict[str, str]:
        if not auth:
            return {}
        if self._token is None:
            raise RuntimeError("还没登录：先 await client.login(...)")
        return {"Authorization": f"Bearer {self._token}"}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Mapping[str, Any] | None = None,
        auth: bool = True,
    ) -> Any:
        response = await self._client.request(
            method,
            path,
            params=params,
            json=json_body,
            headers=self._headers(auth),
        )
        body = response.json()
        if response.status_code >= 400:
            raise FinError(
                response.status_code,
                body.get("code", "UNKNOWN"),
                body.get("message", f"{method} {path} 失败"),
            )
        return body

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return await self._request("GET", path, params=params)

    async def _post(
        self,
        path: str,
        body: Mapping[str, Any] | None = None,
        *,
        auth: bool = True,
    ) -> Any:
        return await self._request("POST", path, json_body=body, auth=auth)

    async def _put(self, path: str, body: Mapping[str, Any] | None = None) -> Any:
        return await self._request("PUT", path, json_body=body)

    # ---- 认证 ------------------------------------------------------ #

    async def login(self, username: str, password: str) -> None:
        # auth=False：登录时还没有 token，不能走带鉴权的分支
        body = await self._post(
            "/api/login",
            {"username": username, "password": password},
            auth=False,
        )
        # 登录响应只有 token 一个字段在这里被用到
        self._token = cast(str, body["token"])

    # ---- 查询 ------------------------------------------------------ #

    async def departments(self) -> list[Department]:
        # 响应形状由财务 API 保证，见 docs/03-finance.md
        return cast(list[Department], await self._get("/api/meta/departments"))

    async def cost_centers(self, dept_code: str) -> list[CostCenter]:
        return cast(
            list[CostCenter],
            await self._get("/api/meta/cost-centers", {"dept": dept_code}),
        )

    async def accounts(self) -> list[AccountNode]:
        return cast(list[AccountNode], await self._get("/api/meta/accounts"))

    # ---- 凭证 ------------------------------------------------------ #

    async def create_voucher(self, payload: VoucherInput) -> CreateResult:
        """建单。单号重复会抛 FinError(409, "DUPLICATE_DOC")。"""
        return cast(CreateResult, await self._post("/api/vouchers", payload))

    async def save_voucher(self, voucher_id: int, payload: VoucherInput) -> SaveResult:
        """覆盖保存整张单据。校验失败时 ok=False，errors 里是字段级错误。"""
        return cast(
            SaveResult,
            await self._put(f"/api/vouchers/{voucher_id}", payload),
        )

    async def find_by_external_ref(self, external_ref: str) -> Voucher | None:
        """按外部单号查已有凭证。幂等的关键：先查再建。"""
        page = cast(
            VoucherPage,
            await self._get("/api/vouchers", {"external_ref": external_ref}),
        )
        items = page["items"]
        return items[0] if items else None

    async def get_voucher(self, voucher_id: int) -> VoucherDetail:
        return cast(VoucherDetail, await self._get(f"/api/vouchers/{voucher_id}"))
