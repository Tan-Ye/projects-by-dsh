"""配置：全部来自环境变量，默认值写在代码里。

不引 python-dotenv，`_load_dotenv` 只做最小实现：够读一个 .env 就行。
"""

from __future__ import annotations

import os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent  # systems/fin
REPO = BASE.parents[1]                         # waybill/


def _load_dotenv(path: Path) -> None:
    """已存在的环境变量不覆盖。"""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BASE / ".env")

PORT = int(os.environ.get("FIN_PORT", "8200"))
DB_PATH = Path(os.environ.get("FIN_DB") or (BASE / "fin.db"))
VALIDATE_DELAY_MS = int(os.environ.get("FIN_VALIDATE_DELAY_MS", "800"))
TOKEN_TTL = int(os.environ.get("FIN_TOKEN_TTL", "900"))
ADMIN_TOKEN = os.environ.get("FIN_ADMIN_TOKEN", "dev-admin-token")
DIST_DIR = BASE / "web" / "dist"

# 只在开发时放行 Vite dev server；生产同源部署，不需要 CORS
DEV_ORIGINS = ["http://127.0.0.1:5173", "http://localhost:5173"]
