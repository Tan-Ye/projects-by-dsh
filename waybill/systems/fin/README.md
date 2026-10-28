# 财务系统（目标系统）

agent 的写入端：SPA + FastAPI，考的是"能不能写对"。

完整设计见 [docs/03-finance.md](../../docs/03-finance.md)，数据层设计见 [DATABASE.md](DATABASE.md)。

## 跑起来

```bash
# 1. 装依赖
python -m pip install -r requirements.txt

# 2. 起服务
python systems/fin/run.py                # http://127.0.0.1:8200
python systems/fin/run.py --port 8201
```

前端（开发时）：

```bash
cd systems/fin/web
pnpm install
pnpm dev        # http://127.0.0.1:5173，/api 代理到 8200
pnpm build      # 产物 web/dist，由 FastAPI 托管
```

## 当前进度

| 阶段 | 内容 | 状态 |
|---|---|---|
| 0 | 骨架：入口、配置、依赖注入、SPA 托管 | ✅ |
| 1 | 数据层：建表、种子、查询函数 | ✅ |
| 2 | 认证与 meta 接口 | ✅ |
| 3 | 凭证：建单 / 整单保存 / 列表 / 详情 | ✅ |
| 4 | 保存时校验、两步审批（maker → checker） | ✅ |
| 5 | 前端 SPA（React 19 + AntD） | ✅ |
| 6 | 漂移档位与评测接口 | 部分（`/api/state` 已通，`/api/_reset` 未做） |
| 7 | 部署 | 待做 |

未实现的接口一律返回 **501**，并带上所属阶段——骨架能跑，但不假装能用。

## 目录

```
systems/fin/
├── run.py                 # 入口，把本目录加进 sys.path 后起 uvicorn
├── .env.example
├── schema.sql（在 app/ 下）
├── app/
│   ├── config.py          # 全部配置来自环境变量
│   ├── db.py              # 连接 + get_db 依赖 + 种子 + 查询
│   ├── deps.py            # 认证依赖（current_user / require_maker / require_checker）
│   ├── validation.py      # 保存时的校验规则
│   ├── errors.py          # 统一错误响应
│   ├── main.py            # FastAPI 装配、CORS、SPA fallback
│   └── routers/
│       ├── internal.py    # /health、/api/state、/api/_reset
│       ├── auth.py        # /api/login
│       ├── meta.py        # 科目、部门、成本中心
│       └── vouchers.py    # 凭证：建单 / 保存 / 列表 / 详情 / 送审 / 复核
└── web/                   # 前端源码，构建产物在 web/dist
```

## 环境变量

见 `.env.example`。几个关键的：

| 变量 | 默认 | 说明 |
|---|---|---|
| `FIN_PORT` | `8200` | 端口 |
| `FIN_VALIDATE_DELAY_MS` | `800` | 保存时的校验延迟，测试时可调小 |
| `FIN_TOKEN_TTL` | `900` | token 有效期（秒） |
| `FIN_ADMIN_TOKEN` | `dev-admin-token` | `/api/_reset` 的通行证 |

## 约定

- 金额一律用**分**（整数），接口不出现浮点
- 错误一律带结构化 `code`
- 校验失败返回 **200 + `{ok:false, errors:[]}`**，不是 4xx
- 凭证状态：`draft` → `pending` → `submitted`。**复核接口只对 `checker` 开放**，`maker` 调用返回 403
