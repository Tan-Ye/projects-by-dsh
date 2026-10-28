# 系统设计

## 一、进程划分

```
┌────────────────────────────────────────────────────┐
│  Web 控制台 (React SPA)                             │
│  任务列表 / 审批页 / Trace 查看器 / 配方管理 / 报表    │
└──────────────────┬─────────────────────────────────┘
                   │ REST + SSE
┌──────────────────▼─────────────────────────────────┐
│  Agent API (FastAPI)                               │
│  编排 · 状态机 · 配方版本 · 核验 · 审计投影 · 权限     │
└──────┬──────────────────────────────┬──────────────┘
       │ Postgres（唯一真相源）         │ Redis（事件分发）
┌──────▼──────────────────────────────▼──────────────┐
│  Worker (Python + Playwright)                      │
│  locate → act → assert → 自愈 → 证据采集 → 回传      │
└──────┬─────────────────────────────────────────────┘
       │
   ┌───▼────┐              ┌──────────┐
   │ OA 仿真 │              │ 财务仿真  │
   └────────┘              └──────────┘
```

**Worker 必须独立进程**：浏览器是最不稳定的部分（内存泄漏、页面卡死、被风控），它崩溃时不能把 API 一起带走。独立之后还能横向扩展，并行跑评测。

**Postgres 当队列**（`SELECT ... FOR UPDATE SKIP LOCKED`）：这个场景每天几十到几百单，吞吐完全够；换来的是任务状态和业务数据在同一个事务里。Redis 只做 SSE 的事件分发。

## 二、数据模型

| 表 | 作用 | 关键字段 |
|---|---|---|
| `recipes` | 配方（可重放的流程定义） | `spec(JSONB)` `version` `status` `stats` |
| `tasks` | 业务任务 | `recipe_id` `input` `idempotency_key` `status` |
| `runs` | 一次执行 | `mode(explore/replay/repair)` `status` `result` `cost` |
| `steps` | 一步动作（审计核心） | `seq` `phase` `intent` `action` `outcome` `assertions` |
| `evidence` | 证据 | `type` `storage_key` `hash` `step_id` |
| `judgments` | LLM 的业务判断 | `kind` `options` `chosen` `rationale` `confidence` |
| `verifications` | 核验结果 | `layer` `passed` `reason_code` `expected/actual` |
| `human_gates` | 人工闸门 | `reason` `payload` `decision` `decided_by` |
| `events` | append-only 事件流 | `entity` `event` `actor` `hash` |

两个要点：

- `steps` 里 **`intent` 由 LLM 写，`action`/`outcome` 由运行时写**，字段级标注来源。
- `events` 做**链式哈希**（`hash = H(prev_hash + payload)`），成本很低，但能证明日志没被事后篡改。

## 三、执行模型

```
Task: pending → queued → running ──→ succeeded
                            │
                            ├──→ waiting_human ──(人处理后)→ running / cancelled
                            └──→ failed
```

Run 内部：

```
① 领取任务（SKIP LOCKED，幂等键冲突则拒绝）
② 逐步骤重放：locate → act → assert
③ 失败分支：
   · locate 失败 → repair：LLM 重定位 → 成功则回写配方、版本+1
   · assert 失败 → 重试 2 次 → 仍失败 → waiting_human
④ 全部完成 → 三层核验
⑤ 核验通过 → succeeded（草稿就绪，等送审）
⑥ 人处理 → 提交审批 → 凭证 pending → 复核通过 → 凭证 submitted；任务状态不再变化
```

`succeeded` 的准确含义是**agent 侧做完了**：草稿已保存、校验通过、等着人处理。送审和复核是产品层的动作，由人执行，不改任务状态——这样"跑通"和"卡住"才是两个可区分的信号。

凭证侧是三步：`draft`（可改）→ `pending`（等复核）→ `submitted`（已入账）。agent 最多把单据推到 `pending`，**`submitted` 只有 checker 能到达**。

**自愈的定位策略链**（成本从低到高，逐级降级）：

`data-testid` → `aria-label` → 文本锚点 → 结构路径 → **LLM 重定位**

前四级本地打分，低于阈值才调 LLM。90% 的步骤零 token 成本，只有真漂移才花钱。

## 四、审计模型

### 4.1 三层粒度

| 层 | 内容 | 给谁看 |
|---|---|---|
| L1 业务层 | 从 OA 单 BX-0912 读 3 条明细 → 财务建凭证 PZ-1130 | 审批人 |
| L2 步骤层 | 每步意图 + 动作 + 断言结果 + 截图 | 审批人 / 开发 |
| L3 证据层 | DOM 快照、网络请求响应、可回放 | 开发 |

审批人默认只看 L1，点字段才下钻到 L2，再点才是 L3。**默认收起、按需下钻**——把全部日志铺给人看等于没做。

### 4.2 字段级 provenance

不是"记录日志"，而是每个写入财务的字段都带一条来源链：

```json
{
  "field": "debit_amount",
  "value": 1286.00,
  "source": {"system": "OA", "doc": "BX-2024-0912", "row": 2, "field": "金额"},
  "raw": "￥1,286元",
  "transform": "strip_currency + to_decimal",
  "judgment_id": null,
  "evidence_id": "ev_7f3a"
}
```

带判断的字段多一层，把备选项和置信度也存下来：

```json
{
  "field": "account_code",
  "value": "6601.03",
  "source": {"system": "OA", "field": "费用说明"},
  "raw": "客户拜访打车费",
  "transform": "llm_classify",
  "judgment_id": "jd_91c2",
  "alternatives": [{"code": "6601.01", "label": "差旅费", "confidence": 0.31}],
  "confidence": 0.88
}
```

审批人点"6601.03"，看到的是：原文 → 为什么判成交通费 → 第二候选是什么 → 置信度多少。**这才是他能判断对错的东西**，而不是一串点击记录。

置信度低于阈值（0.7）自动生成 `human_gate`，必须显式确认才能过。

### 4.3 两种视图，同一份数据

- **审批视图**：结论卡片 + 字段依据链 + 风险提示 + 确认按钮
- **调试视图**：时间线 + 步进回放 + 两次 run 的 diff（哪个锚点漂了、修成什么）

同一份 `steps`/`evidence`/`judgments` 投影出两套 UI。第三用途是评测：所有 `failed` 的 run 带原因码，直接进 eval 集。

## 五、核验与失败分类

三层核验：

1. **动作级**：元素出现/消失、loading 结束、文本匹配
2. **单据级**：字段值 == 期望值，明细合计 == 表头金额
3. **跨系统对账**：OA 汇总 == 财务合计；附件张数 == 明细行数；单号未入账

失败必须落原因码，这套码表就是评测维度：

`LOCATE_DRIFT` / `ASSERT_MISMATCH` / `MAPPING_MISSING` / `DUPLICATE_DOC` / `ATTACHMENT_COUNT` / `AMOUNT_MISMATCH` / `AUTH_EXPIRED` / `TIMEOUT`

## 六、八条设计决策

1. Worker 与 API 分离——浏览器会崩，编排不能崩
2. 重放不调 LLM——确定性和成本，只有漂移才付费
3. 配方版本化——自愈即升级，可回滚，可统计锚点稳定性
4. LLM 写意图、运行时写事实——审计可信的前提
5. 字段级 provenance——可追溯性优于日志完整性
6. Postgres 当队列 + 幂等键——一致性优先，防重复入账
7. 提交必须人点——`maker` / `checker` 分权，agent 连按钮都看不到
8. 证据分层保留——截图只留关键步，DOM 只留 diff

## 七、明确不做

- **不做 OCR**（发票信息从 OA 结构化字段取）——一碰图像识别就偏离主线
- 不做多租户和 RBAC，单用户 + 简单角色
- 不做通用录制器，只支持 OA → 财务这一条链路
- 不做任意网站的通用 agent
