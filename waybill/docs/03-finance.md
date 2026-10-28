# 财务系统（目标系统）

agent 的**写入端**。OA 考"能不能读准"，这里考"能不能写对"：联动、校验、幂等、失败恢复。

## 一、为什么是 SPA，不是 SSR

**结论：传统 SPA（CSR）。**

| 理由 | 说明 |
|---|---|
| 异构 | OA 已经是 SSR + 整页刷新 + cookie。财务再做 SSR，两个靶子考同一类问题，项目最值钱的能力（扛住客户端渲染的不确定性）就丢了 |
| 收益为零 | 登录后的表单应用，没有 SEO、没有首屏内容价值，交互全部在客户端。用 Next.js 做后台，最后基本整页 `'use client'`，绕一圈回到 SPA 还多背一个 Node 运行时 |
| 市场一致 | 国内费控 SaaS、企业财务中台的主流就是 React SPA + 独立 API |

顺带一条认知：框架不影响 agent "看到什么"，但决定它 "什么时候、以什么顺序、在哪个位置"看到。

- 受控输入：值在 DOM 里，React 的 state 里可能是空的
- Portal：弹窗和 toast 渲染在 `body` 末尾，不在表单子树里
- 异步渲染：点击后 DOM 先空一下再填

**异构的不是外观，是失败模式。**

## 二、技术栈

| 层 | 选型 |
|---|---|
| 前端 | Vite + React 19 + TypeScript + Ant Design 5 + React Router |
| 后端 | FastAPI + Pydantic（已通过 `tools/bootstrap.py` 验证可安装） |
| 存储 | SQLite `fin.db`（外部系统仿真，不与 Waybill 主库共用） |
| 运行 | 前端 `pnpm build` → `dist/`，由 FastAPI 托管静态文件 + 提供 `/api/*` |

端口 **8200**。

## 三、数据模型

金额一律按「分」存整数，避免浮点误差。

```
accounts        code(PK) name parent_code level is_leaf is_active sort
departments     code(PK) name is_active
cost_centers    code(PK) name dept_code is_default is_active
vouchers        id voucher_no external_ref(UNIQUE) voucher_date summary
                dept_code attachment_count status created_by
                created_at saved_at submitted_at submitted_by
                approved_at approved_by review_note
voucher_lines   id voucher_id seq account_code cost_center debit_cents summary
voucher_errors  id voucher_id field code message created_at
users           username password_hash display_name role(maker/checker)
sessions        token username created_at expires_at
```

**派生数据不落库。** 借方合计和"是否校验通过"都能从别的表算出来，存一份就多一个会不一致的地方：

```sql
-- 借方合计
SELECT COALESCE(SUM(debit_cents), 0) FROM voucher_lines WHERE voucher_id = ?;

-- 校验是否通过：保存过，且最近一次没留下错误
saved_at IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM voucher_errors WHERE voucher_id = ?
);
```

单张凭证只有几行，走 `ix_lines_voucher` 索引，代价可以忽略；换来的是"合计和明细不可能对不上"。

`status`：`draft` → `pending` → `submitted`（→ `voided`）；`pending` 可以被驳回退回 `draft`。

- `draft`：可编辑，没有凭证号
- `pending`：已提交审批，字段锁定，等待复核
- `submitted`：复核通过入账，字段锁定，已分配凭证号

`voucher_no` 在**复核通过时**分配：`PZ-{yyyyMMdd}-{seq:04d}`。草稿和待审批都没有凭证号——"提交了"不等于"入账了"。

驳回会把 `status` 退回 `draft` 并写入 `review_note`，制单人改完可以重新提交。不新建单据，`external_ref` 保持不变。

**角色分离**：

| 动作 | maker | checker |
|---|---|---|
| 建单、编辑、保存 | ✅ | ❌ 403 |
| 提交审批（draft → pending） | ✅ | ❌ 403 |
| 复核通过（pending → submitted） | ❌ 403 | ✅ |
| 复核驳回（pending → draft） | ❌ 403 | ✅ |

agent 用 `maker` 账号，能制单、能送审，**但永远过不了复核那一关**——终审必须是人。权限由服务端强制，不靠前端隐藏按钮。

复核人只读：打开草稿看不到保存按钮，接口也会返回 403。**能改单的人不能复核自己的单**，这条分工只有落在接口上才成立。

## 四、API 契约

认证用 **Bearer token**（不是 cookie），15 分钟过期。

### 认证与元数据

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/login` | `{username, password}` → `{token, expires_at}` |
| GET | `/api/meta/accounts` | 科目树（含 `is_leaf`、`is_active`） |
| GET | `/api/meta/departments` | 部门列表 |
| GET | `/api/meta/cost-centers?dept=CODE` | 该部门可选成本中心（含 `is_default`） |

### 凭证

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/vouchers?status=&external_ref=&page=` | 列表；带 `external_ref` 时可当单号预检用 |
| POST | `/api/vouchers` | **建单 = 首次保存**：body 是整张单据（表头 + 明细），返回 `{id, ok, errors}`。单号已存在 → **409 `DUPLICATE_DOC`** |
| GET | `/api/vouchers/{id}` | 详情 |
| PUT | `/api/vouchers/{id}` | 再次保存（同样是整张单据），服务端延迟 **800ms** 后返回校验结果 |
| POST | `/api/vouchers/{id}/submit` | 提交审批：`draft` → `pending`。maker 和 checker 都能调 |
| POST | `/api/vouchers/{id}/approve` | 复核通过并入账：`pending` → `submitted`，分配凭证号。**仅 `checker`** |
| POST | `/api/vouchers/{id}/reject` | 复核驳回：`pending` → `draft`，body `{note}`。**仅 `checker`** |

**为什么建单就带着整张单据**：新建时前端只有一份内存里的表单，什么都没有落库；点保存才发第一个请求。这样 `voucher_date` / `dept_code` 在建单那一刻必然有值，`NOT NULL` 才站得住。

代价是重复单号要等人填完表头才发现。前端可以在单号失焦时先打一次 `GET /api/vouchers?external_ref=xxx` 预检，但**服务端的 409 才是最终防线**——预检只是省一次白填。

### 错误格式（统一）

传输层错误（认证、权限、冲突、不存在）返回 4xx，body 统一：

```json
{"code": "DUPLICATE_DOC", "message": "外部单号 BX-2024-0912 已存在"}
```

| code | HTTP | 触发条件 |
|---|---|---|
| `AUTH_REQUIRED` / `TOKEN_EXPIRED` | 401 | 未带 token / 过期 |
| `INVALID_CREDENTIALS` | 401 | 用户名或密码错误（不区分是哪一个，避免枚举账号） |
| `NOT_PERMITTED` | 403 | `maker` 角色调用提交接口 |
| `VALIDATION_ERROR` | 422 | 请求体/查询参数不合法（缺字段、类型错），`errors[]` 里带字段路径 |
| `DUPLICATE_DOC` | 409 | 外部单号已存在 |
| `NOT_DRAFT` | 409 | 对非草稿凭证做修改或提交 |
| `NOT_PENDING` | 409 | 对非待审批凭证做复核/驳回 |
| `NOT_VALIDATED` | 409 | 提交时最近一次保存未通过校验 |
| `VOUCHER_NO_CONFLICT` | 409 | 凭证号并发撞号，重试仍失败 |
| `NOT_FOUND` | 404 | 凭证不存在 |

**校验失败不是 4xx。** 保存成功就返回 200，校验结果在 body 里：

```json
{"ok": false, "errors": [
  {"field": "lines[1].account_code", "code": "ACCOUNT_NOT_LEAF",
   "message": "科目 6601.05 不是末级科目"}
]}
```

HTTP 200 也可能是业务失败——真实系统里很常见的坑，agent 不能只看状态码。

`errors[].code` 取值：

`ACCOUNT_NOT_LEAF` / `ACCOUNT_INACTIVE` / `ACCOUNT_NOT_FOUND` /
`COST_CENTER_MISMATCH` / `NO_LINES` / `AMOUNT_INVALID` / `TOTAL_ZERO` /
`ATTACHMENT_REQUIRED`

**所有错误必须带结构化 `code`。** 只返回中文文案的接口给不了 agent 决策依据——它要么解析自然语言（脆弱），要么瞎猜。

## 五、校验规则（保存时）

保存（`PUT /api/vouchers/{id}`）时同步执行，**800ms** 后返回结果；不通过则 `ok=false` 并附 `errors[]`：

1. 至少一行明细
2. 每行金额 > 0
3. 科目存在、启用、且是末级
4. 成本中心存在，且属于凭证表头的部门
5. 附单据数 ≥ 1
6. 借方合计 > 0

校验放在保存而不是提交，是因为 **agent 只负责制单**：它必须在交付前就知道这张单子过不过，而不是等人点提交时才发现错误。

**贷方自动生成**：贷方科目固定为「其他应付款-员工报销」，金额等于借方合计。借贷平衡不作为 agent 的负担——对方科目是系统规则，让 agent 猜就是制造不公平的失败。

## 六、前端交互模型

### 页面

| 路由 | 内容 |
|---|---|
| `/login` | 用户名密码 → token 存 `sessionStorage` |
| `/vouchers` | 列表 + 状态筛选 + 新建 |
| `/vouchers/new` | 录入表单 |
| `/vouchers/:id` | 详情（已提交后只读，显示凭证号） |

History 路由，服务端对未知路径回 `index.html`（否则深链接 404，这是 SPA 最常见的部署坑）。

### 表头

凭证日期、摘要、附单据数、**外部单号**、部门、制单人（只读）

### 明细行

科目（三级联动）、成本中心（依赖部门）、借方金额、摘要

### 联动

```
部门 change  → 重新拉成本中心 → 已选的成本中心被清空
科目一级    → 300ms 后加载二级 → 再加载三级 → 必须选到末级
```

### 保存链路

```
点击"保存"
  → 前端本地校验（必填、金额格式）→ 不通过则行内提示，不发请求
  → PUT /vouchers/{id}（按钮 disabled，文案变"保存中..."）
  → 800ms
      ├─ ok=false → 顶部错误汇总 + 字段高亮，停留本页
      └─ ok=true  → toast（Portal，2 秒）+ 页面上留下"校验通过"状态
```

**成功判据不能靠 toast**——2 秒就没了。正确做法是看响应或页面上留下状态标记。

提交是复核员的动作：`maker` 登录时提交按钮不渲染，直接调接口也会 403。

### 三个必须注意的实现点

- **受控输入**：`input.value = x` 不会更新 React state，提交上去是空值。执行器必须用真实输入事件
- **Portal**：AntD 的下拉、Modal、message 都挂在 `body` 上，按表单容器找元素会全部落空
- **索引重排**：删掉中间一行后，其余行的 `seq` 变了，按"第 3 行"定位会错位

## 七、漂移档位

`?ui=v2` 写入 localStorage，之后一直生效；`?ui=v1` 清除。

| 版本 | 变化 | 测什么 |
|---|---|---|
| v1 | 基线 | — |
| v2 | "保存" → "保存草稿"；成本中心从 `select` 改成 `input` + 联想补全 | 文案漂移、控件类型漂移 |
| v3 | 科目选项标签反转（`6601.03 交通费` → `交通费（6601.03）`）；金额输入加千分位掩码；明细默认 2 行 | 标签解析、输入掩码、初始结构 |

**硬约束：只改呈现，不改语义。** 三个档位下账户编码、金额、成本中心都必须完全一致，`/api/state` 返回逐字节相同——否则自愈率指标会被污染，测出来的是"数据变了"而不是"页面变了"。

## 八、种子数据

### 科目表（2 级和 3 级混合）

```
6601 管理费用
├─ 6601.01 差旅费
├─ 6601.03 交通费
├─ 6601.04 业务招待费
├─ 6601.05 办公费
│   ├─ 6601.05.01 办公用品
│   └─ 6601.05.02 快递费
└─ 6601.09 会议费（已停用，下拉可见但不可选）
```

混合层级是刻意的：有的分支到二级就到底，有的要下到三级。"什么时候算选完"是 agent 必须自己判断的事。

### 部门与成本中心

| 部门 | 默认 | 备选 |
|---|---|---|
| 研发部 `RD` | `CC-RD-01` | `CC-RD-02` |
| 市场部 `MKT` | `CC-MKT-01` | — |
| 销售部 `SALES` | `CC-SALES-02` | `CC-SALES-01` |
| 行政部 `ADM` | `CC-ADM-01` | — |
| 财务部 `FIN` | `CC-FIN-01` | — |
| 人力资源部 `HR` | `CC-HR-01` | — |

**没有 `市场部-华东区`**——这是 T5 卡住的原因。

### 预置凭证

T3 需要一张已经存在的 `external_ref = BX-2024-0912` 的已提交凭证。但 T1 也用这个单号。

所以**每个任务运行前重置数据并按任务夹具播种**，而不是让任务互相依赖。这样五个任务可以任意顺序、独立重跑、并行执行。

## 九、评测接口

### 状态核对（不走 token）

`GET /api/state/{external_ref}`

```json
{
  "voucher_no": null,
  "status": "draft",
  "validated": true,
  "external_ref": "BX-2024-0912",
  "dept_code": "MKT",
  "attachment_count": 1,
  "lines": [{"seq": 1, "account_code": "6601.03", "cost_center": "CC-MKT-01", "debit_cents": 12860}],
  "total_debit_cents": 12860,
  "credit_cents": 12860
}
```

`validated` 表示最近一次保存时校验是否通过。agent 的产物就是一张 `status=draft` 且 `validated=true` 的凭证。

checker 只读这个，**从不读 agent 的自述**。

### 数据重置（评测专用）

`POST /api/_reset` with header `X-Admin-Token`，body `{fixture: "T1"}`。重建数据并套用该任务的预置数据。

agent 不知道也不需要知道这个接口——它出现在文档里只是为了让评测可复现。

## 十、实施顺序

| 阶段 | 内容 | 产出 |
|---|---|---|
| 0 | 骨架：依赖、目录、FastAPI 入口、`checker` 与 `reset` 的空壳 | 服务能起，`/health` 通 |
| 1 | 数据层：建表、种子、查询函数 | `fin.db` 可重建，科目 / 部门 / 成本中心可查 |
| 2 | 认证与 meta 接口 | 登录拿 token，三个 meta 接口返回约定结构 |
| 3 | 凭证草稿的创建与整单保存 | 能建草稿、整单保存 |
| 4 | 保存时校验与角色权限 | 800ms 延迟、错误列表、`maker` / `checker` 分离 |
| 5 | 前端 SPA | 四个页面、三级联动、部门联动、Portal toast |
| 6 | 漂移档位与评测接口 | v1/v2/v3 可切换，`/api/state` 可用 |
| 7 | 部署 | 静态资源与 API 同源，SPA fallback 生效 |

**阶段 4 之前不要动前端。** 接口契约没定死就写 UI，改一次要改两边——这是这类前后端同人项目最常见的返工来源。
