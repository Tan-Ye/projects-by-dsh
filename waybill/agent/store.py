"""执行记录：runs / steps / judgments。

定位：只负责"把发生过的事写下来"，不做调度、不做核验。
状态机、队列、并发留给将来——现在写进去就是过度设计。

DDL 在 schema.sql，SQL 归 SQL，Python 归 Python。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

import config

SCHEMA_FILE = Path(__file__).with_name("schema.sql")

# 当前结构版本。改结构时 +1，并在 _migrate 里补一段迁移。
# 1 = 最初的 runs/steps/judgments
# 2 = 加 tasks 表、runs.task_id
# 3 = 加 steps.target_path（失败时指出是哪个 target）
# 4 = 加 extractions / verifications
# 5 = 加 repairs（自愈记录）
# 6 = tasks.status 增加 resolved、加 gate_actions（人工闸门操作留痕）
# 7 = 加 batches / batch_items、tasks.batch_id（批次扫描）
# 8 = 加 evals（评测结果入库，控制台可看可对比）
SCHEMA_VERSION = 8


def now() -> str:
    """项目约定的定宽时间串，排序即时间序。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def connect() -> sqlite3.Connection:
    # check_same_thread=False：FastAPI 的同步依赖跑在线程池里，
    # 而 async 端点跑在事件循环线程里，同一个请求会跨线程用这个连接。
    # 每个请求各持一条连接，所以并发写不会被共享连接搅乱。
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """建表 + 迁移。必须幂等——每次启动都会跑。"""
    conn = connect()
    try:
        conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
        if _current_version(conn) < SCHEMA_VERSION:
            _migrate(conn)
            conn.execute(
                "INSERT INTO schema_version (version, applied_at) VALUES (?,?)",
                (SCHEMA_VERSION, now()),
            )
            conn.commit()
    finally:
        conn.close()


def _current_version(conn: sqlite3.Connection) -> int:
    """这个库到哪一版了。新库返回 0。"""
    row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    return int(row["v"] or 0)


def _migrate(conn: sqlite3.Connection) -> None:
    """把老库补到当前结构。

    加列用 ALTER TABLE；改约束只能重建表（SQLite 不支持 ALTER CHECK）。
    重建的顺序是：建新表 → 拷数据 → 删旧表 → 改名，全程关外键。
    SQLite 没有 ALTER CHECK，所以 steps.target_path 这种能加列的就加列。

    每一步都要幂等：迁移可能因为上次崩在中途而重跑。
    """
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(runs)")}
    if "task_id" not in columns:
        conn.execute("ALTER TABLE runs ADD COLUMN task_id INTEGER REFERENCES tasks(id)")

    step_columns = {row["name"] for row in conn.execute("PRAGMA table_info(steps)")}
    if "target_path" not in step_columns:
        conn.execute("ALTER TABLE steps ADD COLUMN target_path TEXT")

    if not _tasks_allow_resolved(conn):
        _rebuild_tasks(conn)

    task_columns = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)")}
    if "batch_id" not in task_columns:
        conn.execute("ALTER TABLE tasks ADD COLUMN batch_id INTEGER REFERENCES batches(id)")


def _tasks_allow_resolved(conn: sqlite3.Connection) -> bool:
    """老库的 tasks.status 里没有 resolved。用建表语句判断，比查版本号稳。"""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'tasks'"
    ).fetchone()
    return row is not None and "'resolved'" in (row["sql"] or "")


def _rebuild_tasks(conn: sqlite3.Connection) -> None:
    """重建 tasks 表以放宽 status 约束。

    关外键是必须的：runs.task_id 指向 tasks，删表时外键会让 DROP 失败。
    新表建好后立刻改名回 tasks，所以 runs 里的引用不受影响。
    """
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.executescript(
        """
        CREATE TABLE tasks_new (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            recipe          TEXT NOT NULL,
            inputs          TEXT NOT NULL,
            idempotency_key TEXT NOT NULL UNIQUE,
            status          TEXT NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'running', 'succeeded',
                                              'waiting_human', 'failed', 'resolved')),
            attempts        INTEGER NOT NULL DEFAULT 0,
            last_error      TEXT,
            created_at      TEXT NOT NULL,
            started_at      TEXT,
            finished_at     TEXT
        );

        INSERT INTO tasks_new (id, name, recipe, inputs, idempotency_key, status,
                               attempts, last_error, created_at, started_at, finished_at)
        SELECT id, name, recipe, inputs, idempotency_key, status,
               attempts, last_error, created_at, started_at, finished_at
        FROM tasks;

        DROP TABLE tasks;
        ALTER TABLE tasks_new RENAME TO tasks;
        CREATE INDEX IF NOT EXISTS ix_tasks_status ON tasks(status, id);
        """
    )
    conn.execute("PRAGMA foreign_keys = ON")


def create_run(
    conn: sqlite3.Connection,
    *,
    task_name: str,
    recipe_name: str,
    recipe_version: int,
    external_ref: str | None = None,
    task_id: int | None = None,
) -> int:
    """开一条 run，状态 running。返回 run_id。"""
    cur = conn.execute(
        "INSERT INTO runs (task_id, task_name, recipe_name, recipe_version, external_ref,"
        " status, started_at) VALUES (?,?,?,?,?,'running',?)",
        (task_id, task_name, recipe_name, recipe_version, external_ref, now()),
    )
    conn.commit()
    # lastrowid 的类型是 int | None：插入语句理论上一定有，但类型系统不这么认为
    if cur.lastrowid is None:
        raise RuntimeError("插入 run 失败：没拿到 lastrowid")
    return int(cur.lastrowid)


def finish_run(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    status: str,
    reason_code: str | None = None,
    reason_message: str | None = None,
) -> None:
    conn.execute(
        "UPDATE runs SET status = ?, reason_code = ?, reason_message = ?, finished_at = ?"
        " WHERE id = ?",
        (status, reason_code, reason_message, now(), run_id),
    )
    conn.commit()


def add_steps(
    conn: sqlite3.Connection,
    run_id: int,
    steps: Sequence[Mapping[str, object]],
) -> None:
    """一次写入整轮步骤。步骤是连续产生的，逐条提交没有意义。"""
    if not steps:
        return
    ts = now()
    conn.executemany(
        "INSERT INTO steps (run_id, seq, intent, action, outcome, reason_code,"
        " reason_message, target_path, duration_ms, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            (
                run_id,
                step["seq"],
                step["intent"],
                step["action"],
                step["outcome"],
                step["reason_code"],
                step["reason_message"],
                step["target_path"],
                step["duration_ms"],
                ts,
            )
            for step in steps
        ],
    )
    conn.commit()


def add_judgment(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    summary: str,
    chosen: str | None,
    confidence: float | None,
    rationale: str,
    accepted: bool,
    reason: str,
) -> None:
    conn.execute(
        "INSERT INTO judgments (run_id, summary, chosen, confidence, rationale,"
        " accepted, reason, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (run_id, summary, chosen, confidence, rationale, int(accepted), reason, now()),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# 任务队列
# ---------------------------------------------------------------------------

def enqueue_task(
    conn: sqlite3.Connection,
    *,
    name: str,
    recipe: str,
    inputs: dict[str, str],
    batch_id: int | None = None,
) -> int | None:
    """入队。返回 task_id；重复入队返回 None。

    幂等键由内容算出。批次内的键带 batch_id：
    上一批跑过这张单，不代表这一批不能再跑——财务里没有凭证就该重新做。
    """
    payload = json.dumps(inputs, ensure_ascii=False, sort_keys=True)
    seed = f"{name}|{recipe}|{payload}"
    if batch_id is not None:
        seed += f"|batch:{batch_id}"
    key = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    cur = conn.execute(
        "INSERT OR IGNORE INTO tasks (batch_id, name, recipe, inputs, idempotency_key,"
        " created_at) VALUES (?,?,?,?,?,?)",
        (batch_id, name, recipe, payload, key, now()),
    )
    conn.commit()
    # rowcount 为 0 说明被幂等键挡掉了；lastrowid 可能是 None 也要防
    if not cur.rowcount or cur.lastrowid is None:
        return None
    return int(cur.lastrowid)


def claim_task(conn: sqlite3.Connection) -> dict[str, object] | None:
    """原子地取一条 pending 任务。队列空返回 None。

    UPDATE ... RETURNING 让"选中 + 改状态"发生在同一条语句里，
    不存在"选到了但还没锁"的窗口；SQLite 的写操作本身串行，
    所以多个 worker 也抢不到同一条。
    """
    row = conn.execute(
        "UPDATE tasks SET status = 'running', started_at = ?, attempts = attempts + 1"
        " WHERE id = (SELECT id FROM tasks WHERE status = 'pending' ORDER BY id LIMIT 1)"
        " RETURNING id, name, recipe, inputs, attempts",
        (now(),),
    ).fetchone()
    conn.commit()
    return dict(row) if row is not None else None


def finish_task(
    conn: sqlite3.Connection,
    task_id: int,
    *,
    status: str,
    error: str | None = None,
) -> None:
    conn.execute(
        "UPDATE tasks SET status = ?, finished_at = ?, last_error = ? WHERE id = ?",
        (status, now(), error, task_id),
    )
    conn.commit()


def get_task(conn: sqlite3.Connection, task_id: int) -> dict[str, object] | None:
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return dict(row) if row is not None else None


# ---------------------------------------------------------------------------
# 人工闸门
# ---------------------------------------------------------------------------

def list_gate(conn: sqlite3.Connection) -> list[dict[str, object]]:
    """等人工处理的任务，附带最近一次运行的信息。"""
    rows = conn.execute(
        "SELECT t.id AS task_id, t.name, t.recipe, t.attempts, t.created_at,"
        " t.last_error, r.id AS run_id, r.external_ref, r.reason_code,"
        " r.reason_message, r.finished_at"
        " FROM tasks t"
        " LEFT JOIN runs r ON r.id = ("
        "   SELECT id FROM runs WHERE task_id = t.id ORDER BY id DESC LIMIT 1)"
        " WHERE t.status = 'waiting_human'"
        " ORDER BY t.id DESC"
    ).fetchall()
    return [dict(row) for row in rows]


def _gate_action(
    conn: sqlite3.Connection,
    task_id: int,
    *,
    action: str,
    note: str,
    actor: str,
) -> None:
    conn.execute(
        "INSERT INTO gate_actions (task_id, action, note, actor, created_at)"
        " VALUES (?,?,?,?,?)",
        (task_id, action, note, actor, now()),
    )


def retry_task(
    conn: sqlite3.Connection,
    task_id: int,
    *,
    actor: str,
    note: str = "",
) -> bool:
    """把任务放回队列，等 worker 再跑一次。返回是否真的改动了。

    只允许从等待/失败两个状态重跑——running 可能还有进程在跑。
    """
    with conn:
        cur = conn.execute(
            "UPDATE tasks SET status = 'pending', finished_at = NULL, last_error = NULL"
            " WHERE id = ? AND status IN ('waiting_human', 'failed')",
            (task_id,),
        )
        if cur.rowcount == 0:
            return False
        _gate_action(conn, task_id, action="retry", note=note, actor=actor)
    return True


def resolve_task(
    conn: sqlite3.Connection,
    task_id: int,
    *,
    actor: str,
    note: str,
) -> bool:
    """人已经处理完（通常是去财务系统里手工补齐）。返回是否真的改动了。"""
    with conn:
        cur = conn.execute(
            "UPDATE tasks SET status = 'resolved', finished_at = ?"
            " WHERE id = ? AND status = 'waiting_human'",
            (now(), task_id),
        )
        if cur.rowcount == 0:
            return False
        _gate_action(conn, task_id, action="resolve", note=note, actor=actor)
    return True


def gate_history(conn: sqlite3.Connection, task_id: int) -> list[dict[str, object]]:
    rows = conn.execute(
        "SELECT action, note, actor, created_at FROM gate_actions"
        " WHERE task_id = ? ORDER BY id",
        (task_id,),
    ).fetchall()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# 批次
# ---------------------------------------------------------------------------

def create_batch(
    conn: sqlite3.Connection,
    *,
    name: str,
    oa_username: str,
    status_filter: str,
    max_scan: int,
    created_by: str,
) -> int:
    """开一个批次。只存用户名，不存密码。"""
    cur = conn.execute(
        "INSERT INTO batches (name, oa_username, status_filter, max_scan, status,"
        " created_by, created_at, started_at) VALUES (?,?,?,?, 'running', ?,?,?)",
        (name, oa_username, status_filter, max_scan, created_by, now(), now()),
    )
    conn.commit()
    if cur.lastrowid is None:
        raise RuntimeError("建批次失败：没拿到 lastrowid")
    return int(cur.lastrowid)


def add_batch_item(
    conn: sqlite3.Connection,
    batch_id: int,
    *,
    doc_no: str,
    outcome: str,
    task_id: int | None = None,
    note: str = "",
) -> None:
    conn.execute(
        "INSERT INTO batch_items (batch_id, doc_no, outcome, task_id, note, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (batch_id, doc_no, outcome, task_id, note, now()),
    )
    conn.commit()


def set_batch_item_outcome(
    conn: sqlite3.Connection,
    batch_id: int,
    doc_no: str,
    *,
    outcome: str,
    note: str = "",
) -> None:
    """扫描时先记 queued，真正跑完再回写终态。"""
    conn.execute(
        "UPDATE batch_items SET outcome = ?, note = ? WHERE batch_id = ? AND doc_no = ?",
        (outcome, note, batch_id, doc_no),
    )
    conn.commit()


def update_batch_counts(
    conn: sqlite3.Connection,
    batch_id: int,
    *,
    scanned: int,
    duplicated: int,
    skipped: int,
    queued: int,
) -> None:
    conn.execute(
        "UPDATE batches SET scanned = ?, duplicated = ?, skipped = ?, queued = ?"
        " WHERE id = ?",
        (scanned, duplicated, skipped, queued, batch_id),
    )
    conn.commit()


def finish_batch(
    conn: sqlite3.Connection,
    batch_id: int,
    *,
    status: str,
    reason_code: str | None = None,
    reason_message: str | None = None,
) -> None:
    conn.execute(
        "UPDATE batches SET status = ?, reason_code = ?, reason_message = ?,"
        " finished_at = ? WHERE id = ?",
        (status, reason_code, reason_message, now(), batch_id),
    )
    conn.commit()


def get_batch(conn: sqlite3.Connection, batch_id: int) -> dict[str, object] | None:
    row = conn.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
    return dict(row) if row is not None else None


def list_batches(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, object]]:
    rows = conn.execute(
        "SELECT * FROM batches ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(row) for row in rows]


def abort_stale_batches(conn: sqlite3.Connection, message: str) -> int:
    """服务重启时把"还在跑"的批次收掉。

    批次跑在进程内存里，进程一停它就没了。不处理的话，
    这条记录会永远显示"运行中"，还会让"只能跑一个批次"的锁永远占着。
    """
    cur = conn.execute(
        "UPDATE batches SET status = 'aborted', reason_code = 'PROCESS_RESTART',"
        " reason_message = ?, finished_at = ? WHERE status = 'running'",
        (message, now()),
    )
    conn.commit()
    return cur.rowcount


def batch_items(conn: sqlite3.Connection, batch_id: int) -> list[dict[str, object]]:
    rows = conn.execute(
        "SELECT doc_no, outcome, task_id, note, created_at FROM batch_items"
        " WHERE batch_id = ? ORDER BY id",
        (batch_id,),
    ).fetchall()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# 评测
# ---------------------------------------------------------------------------

def save_eval(
    conn: sqlite3.Connection,
    *,
    label: str,
    total: int,
    passed: int,
    metrics: dict[str, float],
    cases: list[dict[str, object]],
    created_by: str,
) -> int:
    cur = conn.execute(
        "INSERT INTO evals (label, total, passed, metrics, cases, created_by, created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (
            label,
            total,
            passed,
            json.dumps(metrics, ensure_ascii=False),
            json.dumps(cases, ensure_ascii=False),
            created_by,
            now(),
        ),
    )
    conn.commit()
    if cur.lastrowid is None:
        raise RuntimeError("保存评测失败：没拿到 lastrowid")
    return int(cur.lastrowid)


def list_evals(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, object]]:
    rows = conn.execute(
        "SELECT id, label, total, passed, metrics, created_by, created_at"
        " FROM evals ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {**dict(row), "metrics": json.loads(str(row["metrics"]))}
        for row in rows
    ]


def get_eval(conn: sqlite3.Connection, eval_id: int) -> dict[str, object] | None:
    row = conn.execute("SELECT * FROM evals WHERE id = ?", (eval_id,)).fetchone()
    if row is None:
        return None
    return {
        **dict(row),
        "metrics": json.loads(str(row["metrics"])),
        "cases": json.loads(str(row["cases"])),
    }


# ---------------------------------------------------------------------------
# 执行产物（证据）
# ---------------------------------------------------------------------------

def add_extraction(
    conn: sqlite3.Connection,
    run_id: int,
    name: str,
    payload: object,
) -> None:
    """存一份执行产物，带内容指纹。

    写进来的目的是"事后能证明当时读到了什么"，
    所以存原样 JSON，不做任何裁剪。
    """
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    conn.execute(
        "INSERT OR IGNORE INTO extractions (run_id, name, payload, sha256, created_at)"
        " VALUES (?,?,?,?,?)",
        (run_id, name, text, hashlib.sha256(text.encode("utf-8")).hexdigest(), now()),
    )
    conn.commit()


def get_extraction(
    conn: sqlite3.Connection,
    run_id: int,
    name: str,
) -> object | None:
    """按名字取回证据。核验要用它，而不是内存里的变量。"""
    row = conn.execute(
        "SELECT payload FROM extractions WHERE run_id = ? AND name = ?",
        (run_id, name),
    ).fetchone()
    return json.loads(row["payload"]) if row is not None else None


def set_external_ref(conn: sqlite3.Connection, run_id: int, external_ref: str) -> None:
    """读到单号之后回填，这样能按单号反查 run。"""
    conn.execute("UPDATE runs SET external_ref = ? WHERE id = ?", (external_ref, run_id))
    conn.commit()


# ---------------------------------------------------------------------------
# 自愈
# ---------------------------------------------------------------------------

def add_repair(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    recipe_name: str,
    step_seq: int,
    target_path: str | None,
    old_target: object,
    new_target: object,
    confidence: float | None,
    rationale: str,
    outcome: str,
) -> None:
    """记一次自愈尝试。

    失败的也记——"修过但没修好"和"根本没修"是两种完全不同的情况。
    """
    conn.execute(
        "INSERT INTO repairs (run_id, recipe_name, step_seq, target_path, old_target,"
        " new_target, confidence, rationale, outcome, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            run_id,
            recipe_name,
            step_seq,
            target_path,
            json.dumps(old_target, ensure_ascii=False) if old_target is not None else None,
            json.dumps(new_target, ensure_ascii=False) if new_target is not None else None,
            confidence,
            rationale,
            outcome,
            now(),
        ),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# 核验
# ---------------------------------------------------------------------------

def add_verifications(
    conn: sqlite3.Connection,
    run_id: int,
    checks: Sequence[Mapping[str, object]],
) -> None:
    """整批写核验结果。通过的也写——"核对过且一致"本身就是证据。"""
    if not checks:
        return
    ts = now()
    conn.executemany(
        "INSERT INTO verifications (run_id, layer, field, passed, reason_code,"
        " expected, actual, created_at) VALUES (?,?,?,?,?,?,?,?)",
        [
            (
                run_id,
                check["layer"],
                check["field"],
                int(bool(check["passed"])),
                check["reason_code"],
                check["expected"],
                check["actual"],
                ts,
            )
            for check in checks
        ],
    )
    conn.commit()
