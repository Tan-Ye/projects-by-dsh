"""统一错误响应。

契约（docs/03-finance.md）：

    HTTP 4xx  →  {"code": "DUPLICATE_DOC", "message": "外部单号已存在"}

校验失败不走这里 —— 它是 200 + {"ok": false, "errors": [...]}，
因为"保存成功了但校验没过"不是请求错误。
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# 框架自己抛的 404 / 405 也要套成同一套格式，否则前端要写两套解析
_CODE_BY_STATUS = {
    400: "BAD_REQUEST",
    401: "AUTH_REQUIRED",
    403: "NOT_PERMITTED",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
}


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def not_implemented(phase: int, what: str) -> ApiError:
    return ApiError(501, "NOT_IMPLEMENTED", f"{what}尚未实现（阶段 {phase}）")


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _handle(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            {"code": exc.code, "message": exc.message},
            status_code=exc.status_code,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            {
                "code": _CODE_BY_STATUS.get(exc.status_code, "ERROR"),
                "message": str(exc.detail),
            },
            status_code=exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        """请求体/查询参数不合法（比如登录少传 password）。

        FastAPI 默认返回 {"detail": [...]}，和项目契约对不上，这里翻译成同一套形状。
        loc 的第一段是参数来源（body / query / path），去掉它只留字段路径。
        """
        errors = [
            {
                "field": ".".join(str(part) for part in err["loc"][1:]) or "body",
                "code": err.get("type", "invalid"),
                "message": err.get("msg", "参数不合法"),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            {"code": "VALIDATION_ERROR", "message": "请求参数不合法", "errors": errors},
            status_code=422,
        )
