"""OA 仿真系统：一个刻意做成「老系统」的服务端渲染应用。

设计目标不是好用，而是真实：table 布局、iframe 内嵌明细、没有 data-testid、
金额带货币符号和中文后缀、附件文件名只藏在 title 属性里、会话会过期。

它模拟的是企业里那套没人愿意改的 OA。
"""

from __future__ import annotations

import json
import math
import mimetypes
import os
import re
import secrets
import sys
import time
import urllib.parse
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

import db

BASE = Path(__file__).resolve().parent
STATIC = BASE / "static"

PORT = int(os.environ.get("OA_PORT", "8100"))
SESSION_TTL = int(os.environ.get("OA_SESSION_TTL", "1800"))  # 30 分钟
DEFAULT_UI = os.environ.get("UI_VERSION", "v1")
PAGE_SIZE = 10
LOCK_THRESHOLD = 3
LOCK_SECONDS = 60

# 漂移档位：同一份数据，渲染出不同的 DOM
UI = {
    "v1": {"columns": ["seq", "occurred_on", "description", "amount", "att"], "detail_page_size": None},
    "v2": {"columns": ["seq", "amount", "occurred_on", "description", "att"], "detail_page_size": None},
    "v3": {"columns": ["seq", "occurred_on", "description", "amount", "att"], "detail_page_size": 2},
}

COLUMN_TITLE = {
    "seq": "序号",
    "occurred_on": "发生日期",
    "description": "费用说明",
    "amount": "金额",
    "att": "附件",
}

env = Environment(
    loader=FileSystemLoader(str(BASE / "templates")),
    autoescape=select_autoescape(["html"]),
)
env.filters["yuan"] = db.fmt_yuan
env.globals["STATUS_TEXT"] = db.STATUS_TEXT

SESSIONS: dict[str, dict] = {}
LOCKED: dict[str, dict] = {}

CONN = db.init()


# --------------------------------------------------------------------------
# 会话
# --------------------------------------------------------------------------

def create_session(username: str) -> str:
    token = secrets.token_urlsafe(18)
    SESSIONS[token] = {"username": username, "login_at": time.time(), "expires_at": time.time() + SESSION_TTL}
    return token


def session_of(token: str | None) -> dict | None:
    if not token:
        return None
    sess = SESSIONS.get(token)
    if sess is None:
        return None
    if sess["expires_at"] <= time.time():
        SESSIONS.pop(token, None)
        return None
    return sess


# --------------------------------------------------------------------------
# 请求 / 响应
# --------------------------------------------------------------------------

class Req:
    def __init__(self, method: str, raw_path: str, headers) -> None:
        parts = urllib.parse.urlsplit(raw_path)
        self.method = method
        self.path = urllib.parse.unquote(parts.path)
        self.raw_query = parts.query
        self.query = urllib.parse.parse_qs(parts.query)
        self.headers = headers
        self.form: dict[str, str] = {}
        self.cookies = self._parse_cookies(headers.get("Cookie", ""))

    @staticmethod
    def _parse_cookies(header: str) -> dict[str, str]:
        jar = {}
        for chunk in header.split(";"):
            if "=" in chunk:
                k, v = chunk.split("=", 1)
                jar[k.strip()] = v.strip()
        return jar

    def q(self, name: str, default=None):
        vals = self.query.get(name)
        return vals[0] if vals else default

    def f(self, name: str, default="") -> str:
        return self.form.get(name, default)

    @property
    def session(self) -> dict | None:
        return session_of(self.cookies.get("oa_session"))


class Resp:
    def __init__(self, status: int = 200, body: bytes = b"", content_type: str = "text/html; charset=utf-8"):
        self.status = status
        self.body = body
        self.headers: dict[str, str] = {"Content-Type": content_type}
        self.cookies: list[str] = []

    def cookie(self, name: str, value: str, max_age: int | None = None) -> "Resp":
        parts = [f"{name}={value}", "Path=/", "HttpOnly", "SameSite=Lax"]
        if max_age is not None:
            parts.append(f"Max-Age={max_age}")
        self.cookies.append("; ".join(parts))
        return self


def page(tpl: str, status: int = 200, **ctx) -> Resp:
    html = env.get_template(tpl).render(**ctx)
    return Resp(status, html.encode("utf-8"))


def error_page(req: Req, status: int, heading: str, message: str) -> Resp:
    return page("error.html", status=status, heading=heading, message=message,
                username=req.session["username"] if req.session else None)


def redirect(location: str, status: int = 302) -> Resp:
    resp = Resp(status, b"")
    resp.headers["Location"] = location
    return resp


def json_resp(obj) -> Resp:
    return Resp(200, json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8"), "application/json; charset=utf-8")


def resolve_ui(req: Req) -> tuple[str, bool]:
    asked = req.q("ui")
    if asked in UI:
        return asked, True
    cookie = req.cookies.get("oa_ui")
    if cookie in UI:
        return cookie, False
    return DEFAULT_UI, False


# --------------------------------------------------------------------------
# handlers
# --------------------------------------------------------------------------

def h_root(req: Req, ui: str):
    return redirect("/todo")


def h_login_get(req: Req, ui: str):
    if req.session:
        return redirect("/todo")
    return page("login.html", ui=ui, redirect_to=req.q("redirect", "/todo"), error="", locked=False)


def h_login_post(req: Req, ui: str):
    username = req.f("username").strip()
    password = req.f("password")
    redirect_to = req.f("redirect") or "/todo"

    now = time.time()
    lock = LOCKED.get(username)
    if lock and lock["until"] > now:
        wait = int(lock["until"] - now)
        return page("login.html", status=403, ui=ui, redirect_to=redirect_to,
                    error=f"账号已锁定，请 {wait} 秒后重试", locked=True)

    row = CONN.execute(
        "SELECT username, password_hash FROM users WHERE username=?", (username,)
    ).fetchone()
    if row is None or row["password_hash"] != db.hash_password(password):
        lock = LOCKED.setdefault(username, {"fails": 0, "until": 0.0})
        lock["fails"] += 1
        if lock["fails"] >= LOCK_THRESHOLD:
            lock["until"] = now + LOCK_SECONDS
            lock["fails"] = 0
            return page("login.html", status=403, ui=ui, redirect_to=redirect_to,
                        error=f"密码错误次数过多，账号锁定 {LOCK_SECONDS} 秒", locked=True)
        return page("login.html", status=401, ui=ui, redirect_to=redirect_to,
                    error="用户名或密码错误", locked=False)

    LOCKED.pop(username, None)
    resp = redirect(redirect_to)
    resp.cookie("oa_session", create_session(username))
    return resp


def h_logout(req: Req, ui: str):
    token = req.cookies.get("oa_session")
    if token:
        SESSIONS.pop(token, None)
    resp = redirect("/login")
    resp.cookie("oa_session", "", max_age=0)
    return resp


def h_todo(req: Req, ui: str):
    # 筛选条件放 URL：同一地址永远得到同一批数据，重放和审计都靠这个。
    # 不存会话——agent 不该猜"用户上次选了什么"。
    status = req.q("status", "").strip()
    if status not in db.STATUS_TEXT:
        status = ""

    try:
        page_no = max(1, int(req.q("page", "1")))
    except ValueError:
        page_no = 1

    where = " WHERE d.status = ?" if status else ""
    total = CONN.execute(
        f"SELECT COUNT(*) AS c FROM documents d{where}",
        (status,) if status else (),
    ).fetchone()["c"]

    pages = max(1, math.ceil(total / PAGE_SIZE))
    page_no = min(page_no, pages)

    rows = CONN.execute(
        "SELECT d.doc_no, d.applicant, d.department, d.reason, d.submitted_at, d.status,"
        " (SELECT COALESCE(SUM(l.amount_cents), 0) FROM doc_lines l WHERE l.doc_no = d.doc_no)"
        f" AS total_cents FROM documents d{where} ORDER BY d.doc_no DESC LIMIT ? OFFSET ?",
        ((status,) if status else ()) + (PAGE_SIZE, (page_no - 1) * PAGE_SIZE),
    ).fetchall()

    return page("todo.html", ui=ui, rows=rows, page_no=page_no, pages=pages,
                total=total, status_filter=status, statuses=list(db.STATUS_TEXT.items()),
                username=req.session["username"])


def _load_doc(doc_no: str):
    doc = CONN.execute(
        "SELECT doc_no, applicant, department, reason, submitted_at, status"
        " FROM documents WHERE doc_no=?",
        (doc_no,),
    ).fetchone()
    if doc is None:
        return None, [], []
    lines = CONN.execute(
        "SELECT id, doc_no, seq, occurred_on, description, amount_cents, attachment_count"
        " FROM doc_lines WHERE doc_no=? ORDER BY seq",
        (doc_no,),
    ).fetchall()
    atts = CONN.execute(
        "SELECT id, doc_no, line_seq, filename FROM attachments WHERE doc_no=? ORDER BY id",
        (doc_no,),
    ).fetchall()
    return doc, lines, atts


def h_doc(req: Req, ui: str, doc_no: str):
    doc, lines, atts = _load_doc(doc_no)
    if doc is None:
        return error_page(req, 404, "单据不存在", f"单据 {doc_no} 不存在，或您没有权限查看。")
    approved_at = (datetime.strptime(doc["submitted_at"], "%Y-%m-%d %H:%M")
                   + timedelta(days=1)).replace(hour=9, minute=3).strftime("%Y-%m-%d %H:%M")
    return page("doc.html", ui=ui, doc=doc, lines=lines, atts=atts,
                detail_url=f"/doc/{doc['doc_no']}/detail",
                total_cents=db.sum_cents(lines), approved_at=approved_at,
                username=req.session["username"])


def _cell(column: str, line) -> dict:
    """把一行数据渲染成单元格。列顺序由漂移档位决定，所以按 column 取值。"""
    if column == "amount":
        return {"text": db.fmt_yuan(line["amount_cents"]), "cls": "num"}
    if column == "att":
        return {"text": f"{line['attachment_count']} 张", "cls": ""}
    if column == "occurred_on":
        return {"text": line["occurred_on"], "cls": ""}
    if column == "description":
        return {"text": line["description"], "cls": ""}
    return {"text": str(line["seq"]), "cls": ""}


def h_detail(req: Req, ui: str, doc_no: str):
    doc, lines, atts = _load_doc(doc_no)
    if doc is None:
        return error_page(req, 404, "单据不存在", f"单据 {doc_no} 不存在，或您没有权限查看。")

    cfg = UI[ui]
    size = cfg["detail_page_size"]
    page_no = 1
    pages = 1
    shown = lines
    if size:
        try:
            page_no = max(1, int(req.q("p", "1")))
        except ValueError:
            page_no = 1
        pages = max(1, math.ceil(len(lines) / size))
        page_no = min(page_no, pages)
        shown = lines[(page_no - 1) * size: page_no * size]

    columns = [{"key": k, "title": COLUMN_TITLE[k]} for k in cfg["columns"]]
    rows = [[_cell(k, line) for k in cfg["columns"]] for line in shown]

    return page("detail.html", ui=ui, doc=doc, rows=rows, columns=columns,
                atts=atts, page_no=page_no, pages=pages, total_cents=db.sum_cents(lines))


def h_attachment(req: Req, ui: str, aid: str):
    path = STATIC / "attachments" / f"att-{int(aid)}.svg"
    if not path.exists():
        return Resp(404, b"not found")
    return Resp(200, path.read_bytes(), "image/svg+xml; charset=utf-8")


def h_static(req: Req, ui: str, rest: str):
    path = (STATIC / rest).resolve()
    if not str(path).startswith(str(STATIC.resolve())) or not path.is_file():
        return Resp(404, b"not found")
    ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    if ctype.startswith("text/") or ctype in ("image/svg+xml", "application/javascript"):
        ctype += "; charset=utf-8"
    return Resp(200, path.read_bytes(), ctype)


def h_health(req: Req, ui: str):
    return json_resp({"status": "ok", "system": "oa", "ui": ui,
                      "session_ttl": SESSION_TTL, "docs": CONN.execute("SELECT COUNT(*) AS c FROM documents").fetchone()["c"]})


def h_api_state(req: Req, ui: str, doc_no: str):
    """给评测 checker 用的旁路：只读、不需要登录。agent 不走这里。"""
    doc, lines, atts = _load_doc(doc_no)
    if doc is None:
        return Resp(404, b'{"error":"not found"}', "application/json; charset=utf-8")
    return json_resp({
        "doc_no": doc["doc_no"],
        "applicant": doc["applicant"],
        "department": doc["department"],
        "reason": doc["reason"],
        "status": doc["status"],
        "total_cents": db.sum_cents(lines),
        "lines": [
            {"seq": l["seq"], "occurred_on": l["occurred_on"], "description": l["description"],
             "amount_cents": l["amount_cents"], "attachment_count": l["attachment_count"]}
            for l in lines
        ],
        "attachments": [{"id": a["id"], "line_seq": a["line_seq"], "filename": a["filename"]} for a in atts],
        "line_attachment_sum": sum(l["attachment_count"] for l in lines),
        "attachment_total": len(atts),
    })


ROUTES = [
    ("GET", r"^/$", h_root),
    ("GET", r"^/login$", h_login_get),
    ("POST", r"^/login$", h_login_post),
    ("GET", r"^/logout$", h_logout),
    ("GET", r"^/todo$", h_todo),
    ("GET", r"^/doc/(?P<doc_no>[\w\-]+)$", h_doc),
    ("GET", r"^/doc/(?P<doc_no>[\w\-]+)/detail$", h_detail),
    ("GET", r"^/attachment/(?P<aid>\d+)$", h_attachment),
    ("GET", r"^/static/(?P<rest>.+)$", h_static),
    ("GET", r"^/health$", h_health),
    ("GET", r"^/api/state/(?P<doc_no>[\w\-]+)$", h_api_state),
]

PUBLIC = [
    r"^/login$", r"^/static/", r"^/attachment/", r"^/health$", r"^/api/state/", r"^/favicon\.ico$",
]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "OA-Server/2.3.1"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def do_GET(self) -> None:
        self._handle("GET")

    def do_POST(self) -> None:
        self._handle("POST")

    def _handle(self, method: str) -> None:
        req = Req(method, self.path, self.headers)

        # 统一去掉结尾斜杠：/login/ 和 /login 是同一个页面，不要让它们走进鉴权分支
        if len(req.path) > 1 and req.path.endswith("/"):
            target = req.path.rstrip("/") or "/"
            if req.raw_query:
                target += "?" + req.raw_query
            self._send(redirect(target, 301))
            return

        if method == "POST":
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length).decode("utf-8") if length else ""
            req.form = {k: v[0] for k, v in urllib.parse.parse_qs(body).items()}

        ui, from_query = resolve_ui(req)

        is_public = any(re.match(p, req.path) for p in PUBLIC)
        if not is_public and req.session is None:
            target = req.path + (("?" + req.raw_query) if req.raw_query else "")
            resp = redirect("/login?redirect=" + urllib.parse.quote(target, safe=""))
        else:
            resp = self._route(req, ui)

        if from_query:
            resp.cookies.append(f"oa_ui={ui}; Path=/; Max-Age=604800; SameSite=Lax")
        self._send(resp)

    def _route(self, req: Req, ui: str) -> Resp:
        for method, pattern, handler in ROUTES:
            if method != req.method:
                continue
            match = re.match(pattern, req.path)
            if not match:
                continue
            kwargs = {k: v for k, v in match.groupdict().items()}
            return handler(req, ui, **kwargs)
        return error_page(req, 404, "页面不存在", f"地址 {req.path} 不存在。")

    def _send(self, resp: Resp) -> None:
        self.send_response(resp.status)
        for key, value in resp.headers.items():
            self.send_header(key, value)
        for cookie in resp.cookies:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", str(len(resp.body)))
        self.send_header("X-Powered-By", "OA-Server/2.3.1")
        self.end_headers()
        try:
            if resp.body:
                self.wfile.write(resp.body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # 浏览器或 agent 提前断开，不值得记一条错误


class OAServer(ThreadingHTTPServer):
    # Windows 上 allow_reuse_address 允许两个进程绑同一个端口，请求会随机落到其中一个，
    # 表现成"改了代码一半生效一半不生效"。端口被占时宁可启动失败。
    allow_reuse_address = False
    daemon_threads = True


def main() -> None:
    port = PORT
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    # 反代部署时只监听回环；直接对外才改 0.0.0.0
    host = os.environ.get("OA_BIND_HOST", "127.0.0.1")
    try:
        server = OAServer((host, port), Handler)
    except OSError as exc:
        print(f"启动失败：端口 {port} 已被占用（{exc}）。换个端口或先停掉旧进程。", file=sys.stderr)
        raise SystemExit(1)
    print(f"OA 仿真系统已启动: http://{host}:{port}  (ui={DEFAULT_UI}, session_ttl={SESSION_TTL}s)")
    print("账号: zhangwei / oa123456")

    # 记下 pid，方便 python run.py --stop 干净地停掉服务
    pid_file = BASE / "oa.pid"
    pid_file.write_text(str(os.getpid()), encoding="utf-8")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        pid_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
