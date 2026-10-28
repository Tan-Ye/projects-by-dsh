-- agent 执行记录
--
-- 约定：
--   * 时间用 TEXT，格式 YYYY-MM-DD HH:MM:SS（定宽，字典序即时间序）
--   * 布尔用 INTEGER 0/1
--   * 全部带 IF NOT EXISTS，启动时重复执行不报错

-- 结构版本
--
-- 迁移靠它判断"这个库到哪一版了"。每次改结构就把 store.SCHEMA_VERSION +1，
-- 并在 _migrate 里补一段从旧版到新版的迁移。
CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER NOT NULL,
    applied_at TEXT NOT NULL
);

-- 任务队列
--
-- 并发语义只有一条：UPDATE ... RETURNING 原子地取走一条 pending。
-- 优先级、延迟、心跳回收都不做——现在只有一个 worker，加了也没人用。
--
-- resolved = 人处理完了。它和 succeeded 是两回事：
-- succeeded 是 agent 跑对了，resolved 是"agent 停了，人接手处理掉"。
CREATE TABLE IF NOT EXISTS tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id        INTEGER REFERENCES batches(id),  -- 哪一批扫出来的
    name            TEXT NOT NULL,
    recipe          TEXT NOT NULL,
    inputs          TEXT NOT NULL,          -- JSON：配方参数
    idempotency_key TEXT NOT NULL UNIQUE,   -- 防重复入队
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'succeeded',
                                      'waiting_human', 'failed', 'resolved')),
    attempts        INTEGER NOT NULL DEFAULT 0,
    last_error      TEXT,
    created_at      TEXT NOT NULL,
    started_at      TEXT,
    finished_at     TEXT
);

CREATE INDEX IF NOT EXISTS ix_tasks_status ON tasks(status, id);

-- 批次：一次"登录 → 扫描 → 批量处理"
--
-- 为什么单独一张表：任务是"一单"，批次是"一次操作"。
-- 扫描数、去重数、跳过数、谁启动的、用的哪个 OA 账号，都属于这次操作。
CREATE TABLE IF NOT EXISTS batches (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    oa_username    TEXT NOT NULL,           -- 用的哪个 OA 账号（不存密码）
    status_filter  TEXT NOT NULL DEFAULT '',
    max_scan       INTEGER NOT NULL,
    scanned        INTEGER NOT NULL DEFAULT 0,   -- 列表里读到多少条
    duplicated     INTEGER NOT NULL DEFAULT 0,   -- 批内重复去掉多少条
    skipped        INTEGER NOT NULL DEFAULT 0,   -- 财务已有、跳过的
    queued         INTEGER NOT NULL DEFAULT 0,   -- 实际入队的
    status         TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed', 'aborted')),
    reason_code    TEXT,
    reason_message TEXT,
    created_by     TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    started_at     TEXT,
    finished_at    TEXT
);

-- 批次明细：每个被扫到的单号都要留下结果，包括被跳过的
CREATE TABLE IF NOT EXISTS batch_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id   INTEGER NOT NULL REFERENCES batches(id),
    doc_no     TEXT NOT NULL,
    outcome    TEXT NOT NULL CHECK (outcome IN
               ('queued', 'duplicate', 'existing', 'succeeded', 'waiting_human', 'failed')),
    task_id    INTEGER REFERENCES tasks(id),
    note       TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_batch_items ON batch_items(batch_id, id);

-- 评测结果：一次评测 = 一组用例 + 四个指标
--
-- 存 JSON 而不是拆细表：评测结果只读不查，拆表要 join 三次才拼得回一份报告。
CREATE TABLE IF NOT EXISTS evals (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    label      TEXT NOT NULL,               -- v1 / v2 / after-fix
    total      INTEGER NOT NULL,
    passed     INTEGER NOT NULL,
    metrics    TEXT NOT NULL,               -- JSON：四个指标
    cases      TEXT NOT NULL,               -- JSON：每个用例的结果
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- 人工闸门的操作记录（追加式，不改不删）
--
-- 谁、什么时候、对哪张单做了什么决定——这是审计里"人签字"的那一笔。
CREATE TABLE IF NOT EXISTS gate_actions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    INTEGER NOT NULL REFERENCES tasks(id),
    action     TEXT NOT NULL CHECK (action IN ('retry', 'resolve')),
    note       TEXT NOT NULL DEFAULT '',
    actor      TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_gate_actions_task ON gate_actions(task_id, id);

-- 一次执行
CREATE TABLE IF NOT EXISTS runs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id        INTEGER REFERENCES tasks(id),  -- 哪个任务跑出来的
    task_name      TEXT NOT NULL,           -- 任务文件里的 name
    recipe_name    TEXT NOT NULL,           -- 用的哪份配方
    recipe_version INTEGER NOT NULL,        -- 哪一版：配方会演进，回溯时必须知道
    external_ref   TEXT,                    -- 关联的外部单号
    status         TEXT NOT NULL
                   CHECK (status IN ('running', 'succeeded', 'waiting_human', 'failed')),
    reason_code    TEXT,                    -- 失败原因码，评测按它分类
    reason_message TEXT,
    started_at     TEXT NOT NULL,
    finished_at    TEXT
);

CREATE INDEX IF NOT EXISTS ix_runs_status ON runs(status, started_at);

-- 每一步（审计 L2 层）
CREATE TABLE IF NOT EXISTS steps (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    seq            INTEGER NOT NULL,        -- 配方里的步骤序号
    intent         TEXT NOT NULL,           -- 人话：这一步想干什么
    action         TEXT NOT NULL,           -- 机器动作：goto / fill / extract_table ...
    outcome        TEXT NOT NULL CHECK (outcome IN ('ok', 'failed')),
    reason_code    TEXT,
    reason_message TEXT,
    target_path    TEXT,                    -- 失败时是哪个 target：action / asserts[i]
    duration_ms    INTEGER NOT NULL,
    created_at     TEXT NOT NULL,
    UNIQUE (run_id, seq)
);

CREATE INDEX IF NOT EXISTS ix_steps_run ON steps(run_id, seq);

-- LLM 的判断（审计里"为什么选这个科目"）
CREATE TABLE IF NOT EXISTS judgments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    summary    TEXT NOT NULL,               -- 输入：费用说明
    chosen     TEXT,                        -- 模型选的科目，可能是 NULL
    confidence REAL,
    rationale  TEXT,                        -- 理由
    accepted   INTEGER NOT NULL CHECK (accepted IN (0, 1)),  -- 是否被采信
    reason     TEXT,                        -- 不采信的原因
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_judgments_run ON judgments(run_id);

-- 执行产物：从目标系统读到的原始数据
--
-- 这是审计的 L3 层证据：事后要能回答"当时 OA 上到底写的是什么"。
-- sha256 现在只防手改；等做链式哈希时，它是链条上的一环。
CREATE TABLE IF NOT EXISTS extractions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,            -- 配方里 "as" 的名字：doc / lines
    payload    TEXT NOT NULL,            -- 原样 JSON
    sha256     TEXT NOT NULL,            -- 内容指纹
    created_at TEXT NOT NULL,
    UNIQUE (run_id, name)
);

CREATE INDEX IF NOT EXISTS ix_extractions_run ON extractions(run_id);

-- 核验结果：这张凭证凭什么被认为是对的
--
-- 通过的也写——只记失败的话，没人能区分"核对通过"和"根本没核对"。
CREATE TABLE IF NOT EXISTS verifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    layer       TEXT NOT NULL CHECK (layer IN ('document', 'cross_system')),
    field       TEXT NOT NULL,
    passed      INTEGER NOT NULL CHECK (passed IN (0, 1)),
    reason_code TEXT,
    expected    TEXT,
    actual      TEXT,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_verifications_run ON verifications(run_id);

-- 自愈记录：哪一步的定位坏了、模型建议换成什么、重试结果如何
--
-- 它既是审计（"配方为什么变了"），也是锚点稳定性的数据源：
-- 同一个 target 被修过三次以上，就该人工去改配方了。
CREATE TABLE IF NOT EXISTS repairs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    recipe_name TEXT NOT NULL,
    step_seq    INTEGER NOT NULL,
    target_path TEXT,                       -- action.target / asserts[i].target
    old_target  TEXT,                       -- 原 target 的 JSON
    new_target  TEXT,                       -- 模型建议的 target
    confidence  REAL,
    rationale   TEXT,
    outcome     TEXT NOT NULL CHECK (outcome IN ('retried_ok', 'retried_failed')),
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_repairs_run ON repairs(run_id);
