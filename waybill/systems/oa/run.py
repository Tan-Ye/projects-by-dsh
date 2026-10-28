"""OA 仿真系统启动入口。

    python run.py                 # 默认 v1
    python run.py --ui v3         # 漂移档位
    python run.py --reset         # 重建数据库和种子数据
    python run.py --port 8101
    python run.py --stop          # 停掉正在运行的服务
"""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

argv = sys.argv[1:]

if "--stop" in argv:
    pid_file = BASE / "oa.pid"
    if not pid_file.exists():
        print("没有找到 oa.pid，服务应该没在运行")
        raise SystemExit(1)
    pid = int(pid_file.read_text(encoding="utf-8").strip())
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"已发送停止信号 -> PID {pid}")
    except OSError as exc:
        print(f"停止失败：{exc}（PID {pid} 可能已经不在了）")
    pid_file.unlink(missing_ok=True)
    raise SystemExit(0)

if "--ui" in argv:
    os.environ["UI_VERSION"] = argv[argv.index("--ui") + 1]

if "--reset" in argv:
    import db

    db.init(reset=True)
    print("数据库已重建")

import app  # noqa: E402  （依赖上面的 sys.path 调整）

if __name__ == "__main__":
    app.main()
