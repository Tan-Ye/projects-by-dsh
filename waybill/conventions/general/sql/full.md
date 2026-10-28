# SQL 规范 · 完整版

**适用范围**：所有手写的 SQL 和 DDL。项目特有的补充见 [project/sql.md](../../project/sql.md)。
只有规则看 [rules.md](rules.md)，规则加示例看 [brief.md](brief.md)。

---

## 1. 禁止 `SELECT *`

```sql
-- ✗ 加了一列，读的那一侧毫不知情
SELECT * FROM users WHERE username = ?;

-- ✓ 列名写死
SELECT username, password_hash, display_name, role, is_active
FROM users WHERE username = ?;
```

```sql
-- ✗ 别名加星号也算
SELECT d.*, (SELECT COALESCE(SUM(amount_cents), 0) FROM order_items l WHERE l.order_no = d.order_no)
FROM orders d;

-- ✓ 一样要一条条列出来
SELECT d.order_no, d.customer, d.department, d.reason, d.created_at, d.status,
       (SELECT COALESCE(SUM(l.amount_cents), 0) FROM order_items l WHERE l.order_no = d.order_no) AS total_cents
FROM orders d;
```

三个理由：

1. **类型声明会变成谎话**。Python 那边用 `TypedDict` + `cast`、TS 那边用 `interface`，都靠"列名固定"这个前提。`*` 一加列，类型就悄悄多了个字段，编译器不报、运行时也不报。
2. **多传数据**。将来凭证表有敏感列，`*` 会把整行捞进日志。
3. **改表时看不出影响面**。显式列名让"改这一列会影响谁"变成可搜索的文本。

**唯一例外是 `COUNT(*)`** —— 它不返回任何列。

---

## 2. 参数用 `?` 占位

```python
# ✗ 拼接 = SQL 注入 + 引号转义地狱
conn.execute(f"SELECT id FROM users WHERE username = '{name}'")

# ✓ 占位符 + 元组
conn.execute("SELECT id FROM users WHERE username = ?", (name,))
```

```python
conn.execute(sql, "MKT")     # ✗ 字符串被当成 3 个字符，抛 ProgrammingError
conn.execute(sql, ("MKT",))  # ✓
```

单个参数也要有逗号，`(dept)` 是字符串不是元组。

---

## 3. 类型约定

```sql
amount_cents    INTEGER NOT NULL,                          -- 金额：分
created_at     TEXT NOT NULL,                             -- 时间：YYYY-MM-DD HH:MM:SS
is_active      INTEGER NOT NULL DEFAULT 1
                   CHECK (is_active IN (0, 1))            -- 布尔：0/1
```

| 数据 | 使用 | 禁止 | 原因 |
|---|---|---|---|
| 金额 | `INTEGER`，单位分 | `REAL` / `DECIMAL` | SQLite 没有真 `DECIMAL`，写了也存成浮点 |
| 时间 | `TEXT`，定宽格式 | 各写各的格式 | 定宽字符串排序 = 时间排序 |
| 布尔 | `INTEGER` 0/1 + `CHECK` | `'true'` / `'Y'` | `WHERE x` 才能直接当真假用 |
| 主键 | 业务键 `TEXT`，纯存储 `INTEGER PRIMARY KEY AUTOINCREMENT` | 拿自增 id 当业务编号 | 业务编号要能对外、能重排 |

---

## 4. DDL 约定

```sql
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    role     TEXT NOT NULL CHECK (role IN ('admin', 'user'))
);

CREATE INDEX IF NOT EXISTS ix_orders_status_created
    ON orders(status, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS ux_categories_default
    ON categories(owner_id) WHERE is_default = 1;
```

- **外键写全列名**：`REFERENCES users(username)`，不写 `REFERENCES users`
- **`CHECK` 后面必须带括号**：`CHECK (role IN ('admin','user'))`
- **最后一列后面不加逗号**
- **命名**：表名复数、列 `snake_case`、布尔列 `is_` 开头、索引 `ix_` / `ux_`

SQLite 恰好容忍省略列名的外键，别的数据库不接受——按不会容忍写。

---

## 5. 约束优于代码检查

```sql
external_no TEXT NOT NULL UNIQUE          -- 防重复入账
CHECK (role IN ('admin', 'user'))       -- 角色只有两种

-- 每个部门至多一个默认成本中心
CREATE UNIQUE INDEX ux_categories_default
    ON categories(owner_id) WHERE is_default = 1;
```

不要写"先 SELECT 判断有没有，再 INSERT"——两个请求之间有空档，并发下会双插。让约束抛错，代码捕获后转成业务错误（`IntegrityError` → 409）。

---

## 6. 事务边界

```python
with conn:
    conn.execute("UPDATE orders SET summary = ? WHERE id = ?", (s, vid))
    conn.execute("DELETE FROM order_items WHERE order_id = ?", (vid,))
    conn.executemany("INSERT INTO order_items (...) VALUES (...)", rows)
```

`with conn` 成功自动提交、异常自动回滚。删了明细但插入失败，凭证就变成空单——这种中间态不能存在。

**`executescript()` 会先隐式提交**，只能用在初始化建表，不能混进业务事务。

---

## 7. 索引

```sql
-- 查询：WHERE status = ? ORDER BY created_at DESC
CREATE INDEX ix_orders_status_created ON orders(status, created_at);
```

列顺序：**等值条件的列在前，排序的列在后**。反过来索引用不上。

小表（几十行以内）不建索引，维护成本大于收益。加索引前先看查询计划：

```sql
EXPLAIN QUERY PLAN SELECT ... ;
```

---

## 8. 注释

```sql
expires_at   INTEGER NOT NULL,                 -- unix 秒，直接和 time.time() 比
updated_by TEXT REFERENCES users(username),  -- 审计要记签字人，不只是时间
```

`--` 只写"为什么"，不写"这是什么"——列名已经说明了。

---

## 常见错误

| 写法 | 问题 |
|---|---|
| `SELECT *` / `SELECT d.*` | 类型声明失真、多取数据 |
| `WHERE is_active` | 隐式真假判断，意图不清 |
| `CHECK x IN (0,1)` | 少了括号，语法错误 |
| 最后一列后留逗号 | 语法错误 |
| 建索引漏 `IF NOT EXISTS` | 第二次启动报 "index already exists" |
| 外键不写列名 | 别的数据库不接受，SQLite 恰好容忍 |
| `executescript` 混进事务 | 隐式提交，回滚失效 |
| 先查后插做唯一性 | 并发下双插 |
