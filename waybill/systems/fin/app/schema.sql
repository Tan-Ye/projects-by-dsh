-- 财务仿真系统 · SQLite schema
--
-- 约定：
--   * 金额一律整数「分」，不用浮点
--   * 布尔用 INTEGER 0/1（SQLite 没有 boolean）
--   * 时间用 ISO 字符串；expires_at 用 unix 秒，方便和 time.time() 比较
--   * 全部带 IF NOT EXISTS，启动时重复执行不报错

CREATE TABLE IF NOT EXISTS users (
    username      TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    display_name  TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('maker', 'checker')),
    is_active     INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))  -- 逻辑删除：停用账号，不删行
);

CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    username   TEXT NOT NULL REFERENCES users(username),
    created_at TEXT NOT NULL,
    expires_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    code        TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    parent_code TEXT REFERENCES accounts(code),
    level       INTEGER NOT NULL CHECK (level BETWEEN 1 AND 3),
    is_leaf     INTEGER NOT NULL DEFAULT 0 CHECK (is_leaf IN (0, 1)),
    is_active   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    sort        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS departments (
    code      TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS cost_centers (
    code       TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    dept_code  TEXT NOT NULL REFERENCES departments(code),
    is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
    is_active  INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE INDEX IF NOT EXISTS ix_cost_centers_dept ON cost_centers(dept_code);

-- 每个部门至多一个默认成本中心；非默认行不进这个索引，不受约束
CREATE UNIQUE INDEX IF NOT EXISTS ux_cost_centers_default
    ON cost_centers(dept_code) WHERE is_default = 1;

CREATE TABLE IF NOT EXISTS vouchers (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    voucher_no        TEXT UNIQUE,              -- 草稿为 NULL，提交时才分配
    external_ref      TEXT NOT NULL UNIQUE,     -- 外部单号，重复入账的防线
    voucher_date      TEXT NOT NULL,            -- YYYY-MM-DD
    summary           TEXT NOT NULL DEFAULT '',
    dept_code         TEXT NOT NULL REFERENCES departments(code),
    attachment_count  INTEGER NOT NULL DEFAULT 0 CHECK (attachment_count >= 0),
    status            TEXT NOT NULL DEFAULT 'draft'
                      CHECK (status IN ('draft', 'pending', 'submitted', 'voided')),
    created_by        TEXT NOT NULL REFERENCES users(username),
    created_at        TEXT NOT NULL,
    saved_at          TEXT,                     -- 最后一次保存时间；NULL 表示从没保存过
    submitted_at      TEXT,                     -- 提交审批的时间
    submitted_by      TEXT REFERENCES users(username),  -- 谁提交的：审计要记签字人
    approved_at       TEXT,                     -- 复核通过（入账）时间
    approved_by       TEXT REFERENCES users(username),  -- 复核人：终审签字
    review_note       TEXT                      -- 驳回意见，驳回时写
);

-- 列表页：WHERE status = ? ORDER BY created_at DESC
CREATE INDEX IF NOT EXISTS ix_vouchers_status_created ON vouchers(status, created_at);

-- 派生数据不落库，查询时算（单张凭证只有几行，走 ix_lines_voucher 索引）：
--   借方合计    SELECT COALESCE(SUM(debit_cents), 0) FROM voucher_lines WHERE voucher_id = ?
--   校验通过    saved_at IS NOT NULL AND NOT EXISTS (
--                 SELECT 1 FROM voucher_errors WHERE voucher_id = ?)

CREATE TABLE IF NOT EXISTS voucher_lines (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    voucher_id   INTEGER NOT NULL REFERENCES vouchers(id) ON DELETE CASCADE,
    seq          INTEGER NOT NULL CHECK (seq >= 1),
    account_code TEXT NOT NULL REFERENCES accounts(code),
    cost_center  TEXT NOT NULL REFERENCES cost_centers(code),
    debit_cents  INTEGER NOT NULL CHECK (debit_cents >= 0),
    summary      TEXT NOT NULL DEFAULT '',
    UNIQUE (voucher_id, seq)
);

CREATE INDEX IF NOT EXISTS ix_lines_voucher ON voucher_lines(voucher_id);

CREATE TABLE IF NOT EXISTS voucher_errors (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    voucher_id INTEGER NOT NULL REFERENCES vouchers(id) ON DELETE CASCADE,
    field      TEXT NOT NULL,
    code       TEXT NOT NULL,
    message    TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_errors_voucher ON voucher_errors(voucher_id);
