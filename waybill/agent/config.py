"""agent 的配置。

分两类：

    固定的   目录、端口、超时——部署时也不变，直接写在这里
    会变的   目标系统地址、密钥——上线一定不同，从环境变量读

加载顺序很重要：先读 .env（不覆盖已有环境变量），再读环境变量。
反过来的话，.env 里配的地址永远不生效——这类顺序 bug 最难查。
"""

from __future__ import annotations

import os
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent

# 数据
DB_PATH = AGENT_DIR / "agent.db"

# 配方与任务
RECIPE_DIR = AGENT_DIR / "recipes"
TASK_DIR = AGENT_DIR / "tasks"

# 单步动作的超时（毫秒）：页面卡住时不能无限等
STEP_TIMEOUT_MS = 10_000


# ---------------------------------------------------------------------------
# .env
# ---------------------------------------------------------------------------

def load_env_file(path: Path) -> list[str]:
    """把 KEY=VALUE 读进环境变量，返回实际写入的键名。

    已存在的环境变量不覆盖——命令行里临时设的值优先于文件。
    十二行够用，不引 python-dotenv。
    """
    if not path.is_file():
        return []

    written: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip()
            written.append(key)
    return written


# 在模块导入时加载一次。配置模块的职责就是"把配置准备好"，
# 副作用集中在这里，比散落在各处的 import 里好查。
load_env_file(AGENT_DIR / ".env")


# ---------------------------------------------------------------------------
# 以下从环境变量读——代码里的默认值只保证"零配置能在本地跑起来"
# ---------------------------------------------------------------------------

# 服务端口。上线时同一台机器可能跑多套环境，端口也会变
PORT = int(os.environ.get("AGENT_PORT", "8300"))

# 两个目标系统：上线换成域名，例如 https://oa.example.com
OA_BASE_URL = os.environ.get("OA_BASE_URL", "http://127.0.0.1:8100")
FIN_BASE_URL = os.environ.get("FIN_BASE_URL", "http://127.0.0.1:8200")

# 财务系统：agent 用制单账号。复核永远是人，agent 没有 checker 密码。
FIN_USERNAME = os.environ.get("FIN_USERNAME", "maker")
FIN_PASSWORD = os.environ.get("FIN_PASSWORD", "maker123")

# OA 账号：只在命令行调试时用（控制台由人当场填写，不从环境变量取）
OA_USERNAME = os.environ.get("OA_USERNAME", "zhangwei")
OA_PASSWORD = os.environ.get("OA_PASSWORD", "oa123456")

# 评测旁路：只有评测脚本用，agent 主流程不碰这个接口
FIN_ADMIN_TOKEN = os.environ.get("FIN_ADMIN_TOKEN", "dev-admin-token")

# 控制台登录：内网自用，账号固定。
# 上线前改成环境变量注入，并把 cookie 设为 secure。
CONSOLE_USERS: dict[str, dict[str, str]] = {
    "admin": {"password": "waybill2026", "display": "管理员"},
    "auditor": {"password": "audit2026", "display": "审计员"},
}
CONSOLE_SECRET = os.environ.get("CONSOLE_SECRET", "dev-only-secret-change-me")

# 控制台前端构建产物；存在就由 main.py 托管
WEB_DIST = AGENT_DIR / "web" / "dist"

# LLM
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")


def require_llm_key() -> str:
    """取 API key；没有就立刻抛错。

    不在这里返回空串：空 key 会让请求打到对方才 401，
    错误发生在离原因很远的地方。缺配置应该在启动时就暴露。
    """
    key = os.environ.get("LLM_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "缺少 LLM_API_KEY：在 agent/.env 里配置，或设置同名环境变量"
        )
    return key
