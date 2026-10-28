# SQL · 项目特有规则

只适用于本仓库，覆盖 [general/sql](../general/sql/full.md) 里的同名规则。
冲突时以本文件为准。

---

1. **表结构的唯一准绳是 `systems/fin/app/schema.sql`**。文档里写的列如果和它对不上，以文件为准，并顺手改文档。

2. **`sessions.expires_at` 是时间规则的例外**：存 unix 秒（`INTEGER`），因为它唯一的用途是和 `time.time()` 比大小。其余时间列一律 `TEXT` 定宽格式。

3. **金额列一律 `*_cents`**，`INTEGER`，单位分。没有后缀的金额列视为命名错误。

4. **`vouchers.status` 只有三个值**：`draft` → `submitted`（人提交）→ `voided`（作废）。作废是逻辑删除，不删行——入过账的凭证是账本历史。

5. **`users` 只做逻辑删除**（`is_active`），不硬删。`vouchers.created_by` / `submitted_by` 指着它，硬删会毁掉历史凭证上的签字人。

6. **`external_ref` 上的 `UNIQUE` 是幂等支点**，任何"先查再插"的写法都算违规。重复由约束抛出，代码捕获 `IntegrityError` 转 409。

7. **`ix_vouchers_status_created` 服务于列表页**（`WHERE status = ? ORDER BY created_at DESC`），不要因为"看着没用"删掉。

8. **种子数据写在 `db.py::_seed`，不写在 `schema.sql` 里**。schema 只管结构，数据归代码，这样重建库和灌数据是两个可分开的动作。

9. **`validated` 和 `total_debit_cents` 不落库**，查询时算。不要让它们变成冗余列——冗余列一旦有第二条写入路径就会漂移。
