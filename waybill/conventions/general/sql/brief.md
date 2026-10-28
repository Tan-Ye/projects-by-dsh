# SQL 规则 · 精简版

每条规则配一个能直接抄的示例。只有规则看 [rules.md](rules.md)，要理由看 [full.md](full.md)。

| # | 规则 | 示例 |
|---|---|---|
| 1 | 禁止 `SELECT *`，含 `d.*` | `SELECT id, name FROM t` |
| 2 | 参数用 `?`，传元组 | `conn.execute(sql, ("A001",))` |
| 3 | 金额存整数分 | `amount_cents INTEGER NOT NULL` |
| 4 | 时间存 TEXT ISO | `created_at TEXT NOT NULL` |
| 5 | 布尔存 0/1，查询写 `= 1` | `WHERE is_active = 1` |
| 6 | 业务键用 TEXT，存储用自增 | `id INTEGER PRIMARY KEY AUTOINCREMENT` |
| 7 | 建表建索引带 `IF NOT EXISTS` | `CREATE INDEX IF NOT EXISTS ix_t_c ON t(c)` |
| 8 | 外键写全列名 | `REFERENCES users(username)` |
| 9 | `CHECK` 带括号 | `CHECK (status IN ('new', 'paid'))` |
| 10 | 命名：表复数、列 snake_case | `order_items` / `is_active` / `ix_orders_status` |
| 11 | 唯一性交给约束 | `external_no TEXT NOT NULL UNIQUE` |
| 12 | 多步写操作包一个事务 | `with conn:` |
| 13 | `executescript` 只用于初始化 | `conn.executescript(ddl)  # 仅初始化` |
| 14 | 复合索引等值列在前 | `(status, created_at)` |
| 15 | 小表不建索引 | 几十行以内不加 |
| 16 | `--` 只写"为什么" | `-- 草稿为 NULL，提交时才分配` |

## 完整示例

```sql
CREATE TABLE IF NOT EXISTS orders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no    TEXT UNIQUE,               -- 草稿为 NULL，提交时才分配
    external_no TEXT NOT NULL UNIQUE,      -- 外部单号，防重复
    status      TEXT NOT NULL DEFAULT 'new'
                CHECK (status IN ('new', 'paid', 'void')),
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_orders_status_created
    ON orders(status, created_at);
```

```python
# 参数是元组；多步写入包事务
with conn:
    conn.execute(
        "SELECT id, name FROM categories WHERE owner_id = ? AND is_active = 1",
        (owner_id,),
    )
    conn.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
```
