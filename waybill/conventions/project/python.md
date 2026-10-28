# Python · 项目特有规则

只适用于本仓库，覆盖 [general/python](../general/python/full.md) 里的同名规则。
冲突时以本文件为准。

---

1. **SQL 只写在 `systems/fin/app/db.py`**。路由层、服务层一律调 `db.xxx()`，不得自己拼 SQL——否则 `SELECT *` 禁令和 TypedDict 的对齐关系都会失效。

2. **连接只能从 `Depends(get_db)` 拿**。除 `db.py` 内部的 `init_db()` / `_seed()`，任何地方不得直接 `connect()`。

3. **行类型定义在 `db.py` 顶部**，命名 `XxxRow`，字段与 `schema.sql` 一一对应。改表时三处必须同时改：`schema.sql` 的列、查询的 `SELECT` 列、`XxxRow` 的字段。

4. **金额字段命名一律 `*_cents`**，类型 `int`。看到没有后缀的 `amount`，说明有地方漏了换算。

5. **`init_db()` 必须幂等**：种子数据先判空再插，启动即调用。连跑三次不报错、不重复，才算过关。

6. **`systems/fin/fin.db` 是生成物**。坏了就删了重建，不要手工改数据——手工改出来的状态无法复现。

7. **只有 `db.py` 里的 `get_*` 会做 `is_active` 过滤**。业务展示历史记录时不要复用这些函数，否则停用的部门/账号会在历史凭证里变成空白。

8. **鉴权挂在路由级**，不写进每个 handler：

   ```python
   router = APIRouter(tags=["meta"], dependencies=[Depends(current_user)])
   ```

   只有需要知道"是谁"的接口（比如提交入账要写 `submitted_by`）才在参数里声明 `user: CurrentUser = Depends(...)`。FastAPI 按请求缓存依赖，路由级和参数级同时存在也只执行一次。

   判据：**只要"必须先登录"这个效果 → 路由级；还要知道"是谁" → 参数级。**
