# 数据库设计

财务仿真系统的数据层。SQLite 单文件，八张表。

**目标**：支撑"agent 建单 → 校验 → 人提交"这条链路，并且让评测接口能只读地还原终态。

> 每张表的「约束」列写的是**跟在类型后面的 SQL 片段**，和类型拼起来就是完整定义。
> 可执行的最终版本以 `app/schema.sql` 为准；这份文档解释它为什么长这样。

---

## 一、四条硬约定

| 约定 | 原因 |
|---|---|
| 金额一律 `INTEGER`，单位是**分** | SQLite 没有真正的 `DECIMAL`，写 `DECIMAL(10,2)` 会被存成 REAL，浮点误差照样存在。对账场景里差一分就是一次误判 |
| 时间一律 `TEXT`，格式 `YYYY-MM-DD HH:MM:SS` | SQLite 没有 DATETIME 类型。统一格式后，字符串排序 = 时间排序 |
| 布尔一律 `INTEGER` 0/1 | SQLite 没有 BOOLEAN。列上带 `CHECK (x IN (0,1))` 防止写进别的值 |
| 外键必须 `PRAGMA foreign_keys = ON` | **SQLite 默认关闭外键约束**，不开的话写了 `REFERENCES` 也白写 |

> 一个例外：`sessions.expires_at` 存 **unix 秒（INTEGER）**，因为它唯一的用途是和 `time.time()` 比大小，整数比字符串省事也更快。其余时间字段一律 TEXT。

---

## 二、关系总览

```
users ──< sessions
  │
  └──< vouchers ──< voucher_lines ──> accounts
            │    └──────────────────> cost_centers ──> departments
            └──< voucher_errors
```

- 一张凭证有多行明细、多条校验错误
- 明细行引用科目和成本中心
- 成本中心属于部门；凭证也属于部门（两者必须一致，这是校验规则之一）

---

## 三、表定义

### users

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `username` | TEXT | `PRIMARY KEY` | 业务主键，`sessions` / `vouchers` 直接引用它 |
| `password_hash` | TEXT | `NOT NULL` | 格式见下 |
| `display_name` | TEXT | `NOT NULL` | |
| `role` | TEXT | `NOT NULL CHECK (role IN ('maker', 'checker'))` | 权限靠它强制 |
| `is_active` | INTEGER | `NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))` | 逻辑删除：停用账号，不删行 |

`role` 必须是 `TEXT`：取值是 `'maker' / 'checker'`，用 `INTEGER` 会误导后来看表结构的人——SQLite 动态类型下照样能存字符串，所以这个错误不会被立刻发现。

`password_hash` 存 `pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>`，用标准库 `hashlib.pbkdf2_hmac` 生成。不要明文，也不要裸 `sha256(password)`——那等于没加盐。校验时用 `hmac.compare_digest`，避免时序侧信道。

**为什么是 `is_active` 而不是删行**：`vouchers.created_by` / `submitted_by` 指着 users，硬删会让历史凭证变成"没有制单人的凭证"——外键会直接拦住删除操作。逻辑删除既保住了引用，又能停掉账号。

代价要提前知道：停用不等于消失。**登录和鉴权必须过滤 `is_active = 1`，但历史记录展示不能过滤**，否则三年前的凭证上制单人就成了空白。同一张表，有的查询要滤、有的不能滤，这是软删最容易翻车的地方。

### sessions

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `token` | TEXT | `PRIMARY KEY` | `secrets.token_urlsafe(24)` |
| `username` | TEXT | `NOT NULL REFERENCES users(username)` | 用户只做逻辑删除，永远不会触发这里 |
| `created_at` | TEXT | `NOT NULL` | |
| `expires_at` | INTEGER | `NOT NULL` | unix 秒，直接和 `time.time()` 比 |

`sessions` 的读写都是按主键走，过期清理由登录时顺带做，量级只有几条——不建索引。

**会话是硬删的，和 users 正好相反。** 它是"状态"不是"业务记录"：过期的 token 留着是负担（还能被重放），不是资产。所以过一条删一条，不留历史。

**为什么存库不存内存**：进程重启后 token 还有效，调试时不用反复登录；也是多 worker 部署时唯一可行的做法。

### accounts（科目树）

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `code` | TEXT | `PRIMARY KEY` | `6601` / `6601.05` / `6601.05.01` |
| `name` | TEXT | `NOT NULL` | |
| `parent_code` | TEXT | `REFERENCES accounts(code)` | 顶级为 NULL |
| `level` | INTEGER | `NOT NULL` | 1 / 2 / 3 |
| `is_leaf` | INTEGER | `NOT NULL CHECK (is_leaf IN (0, 1))` | **是否末级** |
| `is_active` | INTEGER | `NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))` | 停用的科目仍要显示，但不能选 |
| `sort` | INTEGER | `NOT NULL` | 同级排序 |

科目树只有 8 行，永远整表读，不建索引。

`is_leaf` 用冗余字段而不是实时算"有没有子节点"，因为树很小但读得极频繁（每次渲染下拉都要全树），实时算要自连接；而且**末级是业务属性**——`6601.05` 下面有子节点所以不是末级，但反过来不成立，不能只靠"有没有孩子"推导。

冗余的代价是可能不一致，所以它**只在种子数据里定义**，运行期不修改。

`is_active` 用来表达"存在但不能选"：`6601.09` 要能被查到（前端显示成灰色），但不能被选中。不要用删除来表达停用。

### departments

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `code` | TEXT | `PRIMARY KEY` | `RD` / `MKT` / `SALES` / `ADM` / `FIN` / `HR` |
| `name` | TEXT | `NOT NULL` | |
| `is_active` | INTEGER | `NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))` | |

纯字典表。保留 `is_active`，因为真实企业里部门会撤销——T5 任务的场景正是"OA 里写了一个财务系统不存在的部门"。

### cost_centers

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `code` | TEXT | `PRIMARY KEY` | `CC-MKT-01` |
| `name` | TEXT | `NOT NULL` | |
| `dept_code` | TEXT | `NOT NULL REFERENCES departments(code)` | |
| `is_default` | INTEGER | `NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1))` | 该部门的默认成本中心 |
| `is_active` | INTEGER | `NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))` | |

```sql
CREATE INDEX IF NOT EXISTS ix_cost_centers_dept ON cost_centers(dept_code);
CREATE UNIQUE INDEX IF NOT EXISTS ux_cost_centers_default
    ON cost_centers(dept_code) WHERE is_default = 1;
```

那条**部分唯一索引**是这张表的关键：把"一个部门只能有一个默认成本中心"变成数据库层面的约束，而不是靠代码自觉。`WHERE` 子句让索引只覆盖 `is_default = 1` 的行，所以同一个部门可以有多个非默认成本中心，但默认的只能有一个。

### vouchers

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | INTEGER | `PRIMARY KEY AUTOINCREMENT` | 存储用，允许空洞 |
| `voucher_no` | TEXT | `UNIQUE` | 提交时才分配，草稿为 NULL |
| `external_ref` | TEXT | `NOT NULL UNIQUE` | OA 单号，幂等键 |
| `voucher_date` | TEXT | `NOT NULL` | `YYYY-MM-DD`，建单时必填 |
| `summary` | TEXT | `NOT NULL DEFAULT ''` | |
| `dept_code` | TEXT | `NOT NULL REFERENCES departments(code)` | 建单时必填 |
| `attachment_count` | INTEGER | `NOT NULL DEFAULT 0 CHECK (attachment_count >= 0)` | 附单据数 |
| `status` | TEXT | `NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'submitted', 'voided'))` | |
| `created_by` | TEXT | `NOT NULL REFERENCES users(username)` | |
| `created_at` | TEXT | `NOT NULL` | |
| `saved_at` | TEXT | — | 最后一次保存时间；NULL 表示从没保存过 |
| `submitted_at` | TEXT | — | 提交前为 NULL |
| `submitted_by` | TEXT | `REFERENCES users(username)` | 谁提交的 |

列表页的查询是 `WHERE status = ? ORDER BY created_at DESC`，用一个复合索引同时覆盖筛选和排序：

```sql
CREATE INDEX IF NOT EXISTS ix_vouchers_status_created ON vouchers(status, created_at);
```

**`external_ref` 上的 UNIQUE 是整套设计的支点。** 它让"同一张 OA 单只能入账一次"变成数据库保证：代码不用"先 SELECT 再 INSERT"，只要捕获 `IntegrityError` 转成 409 即可——重复判定只有一处。

**表头字段为什么是 `NOT NULL`**：建单发生在**第一次保存**，那时候表单已经填完，日期和部门一定有了。

```
新建   ：前端只留一份内存里的表单，不落库
首次保存：POST 整张单据（表头 + 明细）→ 这时才 INSERT，所以 NOT NULL 成立
再次保存：PUT 整张单据 → 覆盖
```

代价是重复单号要等人填完表头才发现。补一个 `GET /api/vouchers?external_ref=xxx` 让前端在单号失焦时预检，服务端 409 仍然是最终防线。

**`submitted_by` 记签字人**：只记时间不记人，审计链条上就缺了一环——出问题时得回答"谁签的字"，而不只是"什么时候签的"。

**衍生数据不落库**：`validated` 和 `total_debit_cents` 都算出来的，不存列。

```sql
-- 借方合计
SELECT COALESCE(SUM(debit_cents), 0) FROM voucher_lines WHERE voucher_id = ?;
-- 是否校验通过：保存过，且没有错误行
SELECT saved_at IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM voucher_errors WHERE voucher_id = ?);
```

单张凭证只有几行，走 `ix_lines_voucher` 足够快；换来的是**永远不会和明细对不上**——冗余列一旦有第二条写入路径就会漂移，而这里根本没有第二条路径。

`voucher_no` 可空且唯一：草稿没有凭证号，提交时才分配。SQLite 的 `UNIQUE` 允许多个 NULL，正好满足这个需求。

**作废也是逻辑删除**：用 `status = 'voided'`，不删行。已经入过账的凭证是账务历史的一部分，删掉等于篡改账本。

### voucher_lines

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | INTEGER | `PRIMARY KEY AUTOINCREMENT` | 存储用 |
| `voucher_id` | INTEGER | `NOT NULL REFERENCES vouchers(id) ON DELETE CASCADE` | |
| `seq` | INTEGER | `NOT NULL CHECK (seq >= 1)` | 第几行，从 1 开始 |
| `account_code` | TEXT | `NOT NULL REFERENCES accounts(code)` | |
| `cost_center` | TEXT | `NOT NULL REFERENCES cost_centers(code)` | |
| `debit_cents` | INTEGER | `NOT NULL CHECK (debit_cents >= 0)` | |
| `summary` | TEXT | `NOT NULL DEFAULT ''` | |

```sql
CREATE INDEX IF NOT EXISTS ix_lines_voucher ON voucher_lines(voucher_id);
```

`UNIQUE (voucher_id, seq)` 写在 `CREATE TABLE` 里，SQLite 会自动建一个内部索引，不需要再显式建。

**两套编号要分清楚**：

| | 谁用 | 允许空洞 |
|---|---|---|
| `id` | 存储、外键 | 允许，删了就是删了 |
| `seq` | 业务："第几行" | **不允许**，必须 1..N 连续 |

`seq` 的语义是位置：凭证打印出来第 3 行、错误信息里的 `lines[1]`、agent 按"第 3 行"找元素，都要和视觉顺序一致。中间缺一个，人第一反应是丢了一行数据。

因为保存是**整单覆盖**（PUT 全量），所以 `seq` 不需要"维护"，每次写入按数组下标 + 1 重新生成即可。`UNIQUE(voucher_id, seq)` 顺便挡住"重排时漏改某行"这类 bug。

### voucher_errors

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | INTEGER | `PRIMARY KEY AUTOINCREMENT` | |
| `voucher_id` | INTEGER | `NOT NULL REFERENCES vouchers(id) ON DELETE CASCADE` | |
| `field` | TEXT | `NOT NULL` | 如 `lines[1].account_code` |
| `code` | TEXT | `NOT NULL` | 如 `ACCOUNT_NOT_LEAF` |
| `message` | TEXT | `NOT NULL` | 给人看的中文说明 |
| `created_at` | TEXT | `NOT NULL` | |

```sql
CREATE INDEX IF NOT EXISTS ix_errors_voucher ON voucher_errors(voucher_id);
```

**只保留最近一次**：每次保存时先删后插，和保存放在同一个事务里。要保留历史得另建快照表，当前阶段不值得。

存它的三个理由：前端刷新后还能看到上次的校验结果；`/api/state` 的 `validated` 和错误明细都从这里取；排查 agent 为什么卡住时有据可查。

---

## 四、三个语法点

这三个最容易写错，单拎出来：

```sql
CHECK (role IN ('maker', 'checker'))    -- CHECK 后面必须带括号，括号里才是表达式
REFERENCES users(username)              -- 列名写全；省略时 SQLite 取主键，别的库不支持
INTEGER PRIMARY KEY AUTOINCREMENT       -- PRIMARY 和 KEY 是两个词
```

---

## 五、种子数据

### 科目树

| code | name | parent | level | is_leaf | is_active |
|---|---|---|---|---|---|
| 6601 | 管理费用 | — | 1 | 0 | 1 |
| 6601.01 | 差旅费 | 6601 | 2 | 1 | 1 |
| 6601.03 | 交通费 | 6601 | 2 | 1 | 1 |
| 6601.04 | 业务招待费 | 6601 | 2 | 1 | 1 |
| 6601.05 | 办公费 | 6601 | 2 | **0** | 1 |
| 6601.05.01 | 办公用品 | 6601.05 | 3 | 1 | 1 |
| 6601.05.02 | 快递费 | 6601.05 | 3 | 1 | 1 |
| 6601.09 | 会议费 | 6601 | 2 | 1 | **0** |

**插入顺序不能反**：父科目必须先于子科目，否则外键过不去。

### 部门与成本中心

| 部门 code | 部门 | 成本中心 | 默认 |
|---|---|---|---|
| RD | 研发部 | CC-RD-01 | ✓ |
| RD | 研发部 | CC-RD-02 | |
| MKT | 市场部 | CC-MKT-01 | ✓ |
| SALES | 销售部 | CC-SALES-01 | |
| SALES | 销售部 | CC-SALES-02 | ✓ |
| ADM | 行政部 | CC-ADM-01 | ✓ |
| FIN | 财务部 | CC-FIN-01 | ✓ |
| HR | 人力资源部 | CC-HR-01 | ✓ |

**没有"市场部-华东区"**——这是 T5 任务会卡住的直接原因，不要为了让数据"完整"把它加进去。

### 账号

| username | 密码 | role |
|---|---|---|
| `maker` | `maker123` | maker |
| `checker` | `checker123` | checker |

---

## 六、schema 要支撑的查询

写索引之前先看查询，别凭感觉加：

| 场景 | SQL 形态 | 用到的索引 | 现状 |
|---|---|---|---|
| 按 OA 单号查凭证（查重） | `WHERE external_ref = ?` | UNIQUE(external_ref) | ✅ |
| 凭证列表 + 状态筛选 | `WHERE status = ? ORDER BY created_at DESC LIMIT ?` | `ix_vouchers_status_created` | ✅ |
| 取凭证及明细 | `WHERE voucher_id = ? ORDER BY seq` | `ix_lines_voucher` | ✅ |
| 某部门的成本中心 | `WHERE dept_code = ? AND is_active = 1` | `ix_cost_centers_dept` | ✅ |
| 科目树 | 全表读（8 行） | 不需要 | — |
| 清理过期会话 | `WHERE expires_at < ?` | 不需要（行数极少） | — |

---

## 七、事务边界

三处写操作各自必须是一个事务，中途失败要整体回滚：

```
建单  ：INSERT vouchers（表头一次到位，NOT NULL 才有意义）
        INSERT voucher_lines × N
        INSERT voucher_errors × M
保存  ：UPDATE vouchers SET 表头..., saved_at=?
        DELETE voucher_lines WHERE voucher_id = ?
        INSERT voucher_lines × N
        DELETE voucher_errors WHERE voucher_id = ?
        INSERT voucher_errors × M
提交  ：UPDATE vouchers SET status='submitted', voucher_no=?, submitted_at=?, submitted_by=?
```

保存那一段尤其要包在一起：如果删除成功、插入失败，凭证就变成一张没有明细的空单。

`total_debit_cents` 和 `validated` 不在这里写——它们是查询时算的，所以不存在"忘记更新"的可能。

**Python 的坑**：`sqlite3` 里 `conn.executescript()` 会先**隐式提交**挂起的事务。所以初始化建表可以用 `executescript`，但业务写操作里绝对不要混用，老老实实 `execute` + `commit`。

---

## 八、凭证号生成

格式 `PZ-{yyyyMMdd}-{序号:04d}`，序号按当天递增。

`SELECT MAX(...) + 1` 在并发下会撞车（两个请求读到同一个 MAX）。正确做法：

1. `voucher_no` 上本来就有 UNIQUE
2. 撞了就接住 `IntegrityError` 重试一次

仿真系统并发极低，但代码里要把这个 catch 写上——这比"假设不会并发"专业得多。

---

## 九、初始化要幂等

`init_db()` 每次启动都会跑，必须保证：

- 建表、建索引全部带 `IF NOT EXISTS`（**索引最容易漏**，漏了第二次启动直接报错）
- 种子数据先判断再插（`SELECT COUNT(*) FROM accounts` 为 0 才插）

连跑三次不报错、不产生重复行，才算过关。

---

## 十、踩坑清单

| 坑 | 后果 |
|---|---|
| 忘了 `PRAGMA foreign_keys = ON` | `REFERENCES` 形同虚设，能插进不存在的部门 |
| `CHECK` 后面漏括号 | 直接语法错误 |
| 最后一列后面留逗号 | 直接语法错误 |
| 建索引漏 `IF NOT EXISTS` | 第二次启动报 "index already exists" |
| 把文档里的约束当整条语句抄 | 约束列只是"类型后面那半截"，不是能独立执行的 SQL |
| 用 REAL 存金额 | `0.1 + 0.2 != 0.3`，对账永远差一分 |
| 时间格式不统一 | 字符串排序错乱，`2024-9-1` 排在 `2024-10-01` 后面 |
| 先 SELECT 再 INSERT 判重 | 并发下同一个单号进两条；应交给 UNIQUE 约束 |
| 用 `id` 当业务序号 | 删掉中间行后，凭证明细会有个空洞 |
| `executescript` 混在事务里 | 隐式提交，回滚不生效 |
| 表头字段设成 `NOT NULL` | 建草稿时就失败——那时候还没部门号 |
| 布尔存字符串 `'true'` | `WHERE is_active` 永远为真 |

---

## 十一、实现状态

| 步骤 | 内容 | 状态 |
|---|---|---|
| 1 | `schema.sql`：八张表 + 索引 | ✅ |
| 2 | `connect()` / `get_db()` / `init_db()` | ✅ |
| 3 | 种子数据 `_seed()`：科目树 → 部门 → 成本中心 → 账号 | ⬜ |
| 4 | 密码哈希 `hash_password` / `verify_password` | ⬜ |
| 5 | 查询函数：`get_user` / `get_accounts` / `get_departments` / `get_cost_centers` | ⬜ |
| 6 | `init_db()` 幂等（连跑两次不报错、不重复插） | ⬜ |

3–6 写在 `app/db.py` 里，那几条 `TODO(阶段 1)` 就是它们的落点。
