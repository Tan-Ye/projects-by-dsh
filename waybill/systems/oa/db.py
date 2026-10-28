"""数据层：SQLite schema、种子数据、发票缩略图生成。

OA 系统是「外部系统」的仿真，所以它有自己的库文件，不与 Waybill 主库共用。
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path

import seed_data

BASE = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("OA_DB") or (BASE / "oa.db"))
ATT_DIR = BASE / "static" / "attachments"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username      TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    display_name  TEXT NOT NULL,
    department    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    doc_no       TEXT PRIMARY KEY,
    applicant    TEXT NOT NULL,
    department   TEXT NOT NULL,
    reason       TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    status       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS doc_lines (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_no           TEXT NOT NULL REFERENCES documents(doc_no),
    seq              INTEGER NOT NULL,
    occurred_on      TEXT NOT NULL,
    description      TEXT NOT NULL,
    amount_cents     INTEGER NOT NULL,
    attachment_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS attachments (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_no   TEXT NOT NULL REFERENCES documents(doc_no),
    line_seq INTEGER NOT NULL,
    filename TEXT NOT NULL
);
"""

STATUS_TEXT = {"pending": "待审批", "approved": "已通过", "rejected": "已驳回"}


def hash_password(raw: str) -> str:
    return hashlib.sha256(("oa::" + raw).encode("utf-8")).hexdigest()


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _invoice_svg(doc_no: str, filename: str, amount_cents: int, seq: int) -> str:
    """画一张像发票的缩略图。内容是假的，但版式要够真。"""
    yuan = f"{amount_cents / 100:,.2f}"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="420" height="240" viewBox="0 0 420 240">
  <rect width="420" height="240" fill="#fbfaf6"/>
  <rect x="6" y="6" width="408" height="228" fill="none" stroke="#c9a227" stroke-width="2"/>
  <text x="210" y="34" font-family="SimSun,serif" font-size="16" text-anchor="middle" fill="#333">增值税电子普通发票</text>
  <text x="20" y="60" font-family="SimSun,serif" font-size="11" fill="#666">发票代码 0110{seq:04d}  发票号码 {doc_no[-6:]}{seq:02d}</text>
  <text x="20" y="78" font-family="SimSun,serif" font-size="11" fill="#666">开票日期 2024-09-10   校验码 8821</text>
  <line x1="16" y1="88" x2="404" y2="88" stroke="#ddd"/>
  <text x="20" y="108" font-family="SimSun,serif" font-size="11" fill="#666">购买方：某某科技（北京）有限公司</text>
  <text x="20" y="128" font-family="SimSun,serif" font-size="11" fill="#666">货物或应税劳务：{filename.split('.')[0][:18]}</text>
  <text x="20" y="152" font-family="SimSun,serif" font-size="13" fill="#333">价税合计（小写）￥{yuan}</text>
  <circle cx="360" cy="190" r="34" fill="none" stroke="#c0392b" stroke-width="2" opacity="0.75"/>
  <text x="360" y="188" font-family="SimSun,serif" font-size="9" text-anchor="middle" fill="#c0392b" opacity="0.85">发票专用章</text>
  <text x="360" y="200" font-family="SimSun,serif" font-size="8" text-anchor="middle" fill="#c0392b" opacity="0.85">某某科技</text>
</svg>"""


def seed(conn: sqlite3.Connection) -> None:
    ATT_DIR.mkdir(parents=True, exist_ok=True)
    for old in ATT_DIR.glob("att-*.svg"):
        old.unlink()

    for user in seed_data.USERS:
        conn.execute(
            "INSERT INTO users (username, password_hash, display_name, department) VALUES (?,?,?,?)",
            (user["username"], hash_password(user["password"]), user["display_name"], user["department"]),
        )

    for doc in seed_data.DOCS:
        conn.execute(
            "INSERT INTO documents (doc_no, applicant, department, reason, submitted_at, status)"
            " VALUES (?,?,?,?,?,?)",
            (doc["doc_no"], doc["applicant"], doc["department"], doc["reason"],
             doc["submitted_at"], doc["status"]),
        )
        for seq, (occurred_on, description, amount_cents, att_count) in enumerate(doc["lines"], start=1):
            conn.execute(
                "INSERT INTO doc_lines (doc_no, seq, occurred_on, description, amount_cents, attachment_count)"
                " VALUES (?,?,?,?,?,?)",
                (doc["doc_no"], seq, occurred_on, description, amount_cents, att_count),
            )
        for line_seq, filename in doc["attachments"]:
            line = conn.execute(
                "SELECT amount_cents FROM doc_lines WHERE doc_no=? AND seq=?", (doc["doc_no"], line_seq)
            ).fetchone()
            amount = line["amount_cents"] if line else 0
            cur = conn.execute(
                "INSERT INTO attachments (doc_no, line_seq, filename) VALUES (?,?,?)",
                (doc["doc_no"], line_seq, filename),
            )
            (ATT_DIR / f"att-{cur.lastrowid}.svg").write_text(
                _invoice_svg(doc["doc_no"], filename, amount, line_seq), encoding="utf-8"
            )


def init(reset: bool = False) -> sqlite3.Connection:
    if reset and DB_PATH.exists():
        DB_PATH.unlink()
    conn = connect()
    conn.executescript(SCHEMA)
    if conn.execute("SELECT COUNT(*) AS c FROM documents").fetchone()["c"] == 0:
        seed(conn)
        conn.commit()
    return conn


def sum_cents(lines: list[sqlite3.Row]) -> int:
    return sum(line["amount_cents"] for line in lines)


def fmt_yuan(cents: int) -> str:
    """OA 的既定风格：带货币符号、千分位、中文后缀。"""
    return f"￥{cents / 100:,.2f}元"
