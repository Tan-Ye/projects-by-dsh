# SQL 规则清单

只有规则，没有解释和示例。要示例看 [brief.md](brief.md)，要理由看 [full.md](full.md)。

1. 禁止 `SELECT *`，包括 `d.*` 这种别名星号；唯一例外是 `COUNT(*)`。
2. 参数一律用 `?` 占位，禁止拼接字符串；传参必须是元组。
3. 金额用 `INTEGER`，单位是分，禁止 `REAL` / `DECIMAL`。
4. 时间用 `TEXT`，格式 `YYYY-MM-DD HH:MM:SS`。
5. 布尔用 `INTEGER` 0/1，列上带 `CHECK (x IN (0, 1))`；查询写 `= 1`，不写隐式判断。
6. 主键：业务键用 `TEXT`，纯存储用 `INTEGER PRIMARY KEY AUTOINCREMENT`。
7. 建表、建索引一律带 `IF NOT EXISTS`。
8. 外键写全列名：`REFERENCES t(col)`，不写 `REFERENCES t`。
9. `CHECK` 后面必须带括号；最后一列后面不加逗号。
10. 命名：表名复数、列 `snake_case`、布尔列 `is_` 开头、索引 `ix_` / `ux_` 前缀。
11. 唯一性用 `UNIQUE` 约束保证，禁止"先 SELECT 再 INSERT"。
12. 一次业务操作里的多条写语句，必须包在同一个事务里。
13. `executescript()` 只能用于初始化建表，不得混入业务事务。
14. 复合索引的列顺序：等值条件的列在前，排序的列在后。
15. 几十行以内的小表不建索引。
16. `--` 注释只写"为什么"，不写"这是什么"。
