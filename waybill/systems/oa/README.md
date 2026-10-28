# OA 仿真系统（源系统）

刻意做成「老系统」的服务端渲染应用：table 布局、iframe 内嵌明细、没有 `data-testid`、金额带货币符号和中文后缀、附件文件名只藏在 `title` 属性里、会话会过期。

它模拟的是企业里那套没人愿意改的 OA。

## 跑起来

```bash
python systems/oa/run.py                 # 默认 v1，端口 8100
python systems/oa/run.py --ui v3         # 漂移档位
python systems/oa/run.py --reset         # 重建数据库和种子数据
python systems/oa/run.py --port 8101
python systems/oa/run.py --stop          # 干净停止（读 oa.pid）
```

启动时会写 `oa.pid`，`--stop` 靠它找到进程。端口被占用时直接报错退出，不会两个进程抢同一个端口。

依赖只有 Jinja2，装在解释器里：`python -m pip install -r requirements.txt`。

打开 <http://127.0.0.1:8100>，账号 `zhangwei / oa123456`。

> 访问 `/login` 时如果已经被重定向到 `/todo`，说明浏览器还带着 `oa_session` cookie。用无痕窗口，或先点右上角"退出"。

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `OA_PORT` | `8100` | 端口 |
| `OA_SESSION_TTL` | `1800` | 会话有效期（秒）。测试会话过期时设小一点，比如 `30` |
| `UI_VERSION` | `v1` | 默认漂移档位 |
| `OA_DB` | `oa.db` | SQLite 文件路径 |

## 页面

| 路由 | 内容 |
|---|---|
| `GET /login` | 登录。密码错 3 次锁 60 秒 |
| `POST /login` | 登录提交 |
| `GET /todo?page=N` | 待办列表，10 条一页，共 18 条 |
| `GET /doc/{doc_no}` | 单据头 + iframe，标题栏有「查看明细页」入口 |
| `GET /doc/{doc_no}/detail` | iframe 内的明细表和附件区，页脚有「返回单据」 |
| `GET /attachment/{id}` | 发票缩略图（SVG） |
| `GET /health` | 健康检查 |
| `GET /api/state/{doc_no}` | **只读核对接口，不需要登录**。给评测 checker 用，agent 不走这里 |

## 漂移档位

`?ui=v2` 会种下 `oa_ui` cookie，之后整站按该档位渲染。

| 档位 | 变化 |
|---|---|
| `v1` | 基线：列顺序 序号/发生日期/费用说明/金额/附件 |
| `v2` | 列顺序变成 序号/**金额**/发生日期/费用说明/附件 |
| `v3` | 明细按 2 行分页（`?p=2`），其余同 v1 |

**漂移只改 UI，不改业务数据。** `/api/state` 在三个档位下返回的内容完全一致——这是自愈率能被测量的前提。

## 种子数据

`seed_data.py`，金额以「分」为单位存整数。18 张单据，其中四张是任务单据：

| 单号 | 用途 |
|---|---|
| `BX-2024-0912` | T1 单行交通费（第 2 页） |
| `BX-2024-0930` | T2 差旅三行混合（第 2 页） |
| `BX-2024-1005` | T4 附件 3 张、明细 2 行（第 1 页） |
| `BX-2024-1011` | T5 部门已撤销（第 1 页） |

其余 14 张是干扰单据，用来让分页成为真问题。

## 冒烟测试

```bash
python tools/smoke_oa.py http://127.0.0.1:8100
```

只校验 HTML 层（页面能开、字段在、漂移生效），不涉及 agent。
