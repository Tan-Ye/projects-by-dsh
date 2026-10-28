"""FastAPI 装配。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import config, db, errors
from .routers import auth, internal, meta, vouchers

PLACEHOLDER = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>财务系统</title></head>
<body style="font-family:system-ui;padding:40px;line-height:1.8">
  <h1>财务仿真系统</h1>
  <p>后端已启动，前端还没构建。</p>
  <p>阶段 5 完成后，<code>python systems/fin/run.py</code> 会自动托管 <code>web/dist</code>。</p>
  <p><a href="/docs">API 文档</a> · <a href="/health">健康检查</a></p>
</body></html>
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="财务仿真系统", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.DEV_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(internal.router)
    app.include_router(auth.router, prefix="/api")
    app.include_router(meta.router, prefix="/api")
    app.include_router(vouchers.router, prefix="/api")

    errors.install(app)

    dist: Path = config.DIST_DIR
    if dist.is_dir():
        assets = dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa_fallback(full_path: str, request: Request):
            """SPA 深链接回 index.html；/api 下的未知路径仍然是 404。"""
            if full_path.startswith("api/"):
                raise errors.ApiError(404, "NOT_FOUND", "接口不存在")
            candidate = dist / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")
    else:

        @app.get("/", response_class=HTMLResponse, include_in_schema=False)
        def placeholder() -> str:
            return PLACEHOLDER

    return app


app = create_app()
