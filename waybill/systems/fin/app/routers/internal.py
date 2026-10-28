"""内部接口：健康检查、评测旁路。"""

from __future__ import annotations

from sqlite3 import Connection

from fastapi import APIRouter, Depends, Header

from .. import config, db
from ..db import fixtures
from ..errors import ApiError

router = APIRouter(tags=["internal"])


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "system": "fin",
        "db": str(config.DB_PATH),
        "validate_delay_ms": config.VALIDATE_DELAY_MS,
        "token_ttl": config.TOKEN_TTL,
        "built_ui": config.DIST_DIR.is_dir(),
    }


@router.get("/api/state/{external_ref}")
def state(external_ref: str, conn: Connection = Depends(db.get_db)) -> dict:
    """给评测 checker 用的只读核对接口，不走 token。

    按外部单号返回凭证终态：agent 说成功不算数，checker 只认这里的数据。
    """
    row = conn.execute(
        "SELECT id FROM vouchers WHERE external_ref = ?", (external_ref,)
    ).fetchone()
    if row is None:
        raise ApiError(404, "NOT_FOUND", f"外部单号 {external_ref} 没有对应凭证")

    detail = db.get_voucher(conn, int(row["id"]))
    if detail is None:
        raise ApiError(404, "NOT_FOUND", f"外部单号 {external_ref} 没有对应凭证")

    # 贷方由系统按借方合计自动生成，一并给出，checker 可以验借贷是否相等
    return {**detail, "credit_cents": detail["total_cents"]}


@router.post("/api/_reset")
def reset(
    payload: dict,
    x_admin_token: str | None = Header(default=None),
    conn: Connection = Depends(db.get_db),
) -> dict:
    """评测专用：清空凭证并按夹具重建起点。

    agent 不知道也不需要知道这个接口，它只为"评测可复现"存在。
    不清用户/部门/科目——那些是系统配置，不是任务数据。
    """
    if x_admin_token != config.ADMIN_TOKEN:
        raise ApiError(403, "NOT_PERMITTED", "admin token 不正确")

    fixture = str(payload.get("fixture") or "").strip().upper()
    if not fixture:
        fixtures.reset(conn)
        return {"ok": True, "fixture": None, "applied": {"vouchers": 0}}

    if fixture not in fixtures.FIXTURES:
        raise ApiError(
            400,
            "UNKNOWN_FIXTURE",
            f"未知夹具 {fixture}，可用：{', '.join(sorted(fixtures.FIXTURES))}",
        )

    return {"ok": True, "fixture": fixture, "applied": fixtures.apply(conn, fixture)}
