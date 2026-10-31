"""agent 服务入口：控制台 API + 前端托管。

一个端口对外：/api/* 是接口，其余路径交给前端路由。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, Response
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from uvicorn import run as uvicorn_run

import config
import store
from api import auth as auth_api
from api import batches as batches_api
from api import evals as evals_api
from api import gaps as gaps_api
from api import gate as gate_api
from api import recipes as recipes_api
from api import runs as runs_api
from api import tasks as tasks_api


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    store.init_db()
    # 批次跑在进程内存里：重启后"运行中"的记录必须收掉，否则状态永远假在跑
    conn = store.connect()
    try:
        aborted = store.abort_stale_batches(conn, "服务重启，未完成的批次作废")
        if aborted:
            print(f"[启动] 收掉 {aborted} 个未完成的批次")
    finally:
        conn.close()

    # 敏感配置还在用默认值时喊一声：本地开发无所谓，线上是事故
    for warning in config.warn_insecure_defaults():
        print(f"[配置] {warning}")

    print(f"[启动] http://{config.BIND_HOST}:{config.PORT}  无头浏览器={config.BROWSER_HEADLESS}")
    yield


app = FastAPI(title="waybill agent", lifespan=lifespan)

app.include_router(auth_api.router)
app.include_router(tasks_api.router)
app.include_router(runs_api.router)
app.include_router(recipes_api.router)
app.include_router(gate_api.router)
app.include_router(batches_api.router)
app.include_router(gaps_api.router)
app.include_router(evals_api.router)


@app.get("/health")
def health() -> dict[str, object]:
    """环境自检：能返回这个，说明 Python、依赖、端口都正常。"""
    return {
        "status": "ok",
        "service": "agent",
        "port": config.PORT,
        "db": str(config.DB_PATH),
        "web_built": config.WEB_DIST.is_dir(),
        "targets": {"oa": config.OA_BASE_URL, "fin": config.FIN_BASE_URL},
    }


# ---------------------------------------------------------------------------
# 前端托管
#
# 路由在 import 时就注册好，不按"dist 存不存在"决定——否则前端重建之后
# 必须重启服务才生效，部署时很容易踩"改了没生效"。
# 目录不存在时 StaticFiles(check_dir=False) 不会报错，SPA 兜底返回 503 说清楚。
# ---------------------------------------------------------------------------

app.mount(
    "/assets",
    StaticFiles(directory=config.WEB_DIST / "assets", check_dir=False),
    name="assets",
)


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str) -> Response:
    """前端路由兜底：具体文件优先，其余交给 index.html。"""
    dist = config.WEB_DIST
    candidate = dist / path
    if path and candidate.is_file():
        return FileResponse(candidate)

    index = dist / "index.html"
    if not index.is_file():
        return PlainTextResponse(
            "控制台前端还没构建：cd agent/web && pnpm build",
            status_code=503,
        )
    return FileResponse(index)


if __name__ == "__main__":
    uvicorn_run(app, host=config.BIND_HOST, port=config.PORT)
