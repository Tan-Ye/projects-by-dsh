"""财务仿真系统启动入口。

    python run.py                 # 8200
    python run.py --port 8201
"""

from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import uvicorn  # noqa: E402

from app import config  # noqa: E402
from app.main import app  # noqa: E402


def main() -> None:
    port = config.PORT
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])

    print(f"财务仿真系统: http://{config.BIND_HOST}:{port}")
    print(f"数据库: {config.DB_PATH}")
    print(f"校验延迟: {config.VALIDATE_DELAY_MS}ms")
    uvicorn.run(app, host=config.BIND_HOST, port=port, log_level="info")


if __name__ == "__main__":
    main()
