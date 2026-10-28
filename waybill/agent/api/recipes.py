"""配方列表：文件是真相，自愈历史在库里。"""

from __future__ import annotations

import json
import sqlite3

from fastapi import APIRouter, Depends

import auth
import config
from api.deps import get_conn

router = APIRouter(prefix="/api/recipes", tags=["recipes"])


@router.get("")
def list_recipes(
    conn: sqlite3.Connection = Depends(get_conn),
    username: str = Depends(auth.current_user),
) -> dict[str, object]:
    repairs = {
        row["recipe_name"]: dict(row)
        for row in conn.execute(
            "SELECT recipe_name, COUNT(*) AS total,"
            " SUM(outcome = 'retried_ok') AS repaired,"
            " MAX(created_at) AS last_at"
            " FROM repairs GROUP BY recipe_name"
        )
    }

    items: list[dict[str, object]] = []
    for path in sorted(config.RECIPE_DIR.glob("*.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))
        if spec.get("fixture"):
            continue
        stats = repairs.get(spec["name"], {})
        items.append(
            {
                "name": spec["name"],
                "version": spec.get("version", 1),
                "base_url": spec.get("base_url", ""),
                "steps": len(spec.get("steps", [])),
                "requires": spec.get("requires", []),
                "repairs": stats.get("total", 0),
                "repaired_ok": stats.get("repaired", 0),
                "last_repair_at": stats.get("last_at"),
            }
        )

    return {"items": items, "total": len(items)}
