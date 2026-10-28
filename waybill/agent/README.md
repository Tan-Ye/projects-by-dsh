# agent

浏览器自动化 + 业务映射 + 财务写入。

## 目录

```
agent/
├── config.py            路径与开关（不跟随 cwd）
├── main.py              FastAPI 服务入口
├── browser/             Playwright 相关
│   └── replay.py        配方加载、渲染、执行、断言
├── fin/                 财务系统对接
│   ├── models.py        财务 API 的契约类型
│   └── client.py        异步客户端
├── business/            纯业务逻辑，不碰 IO
│   ├── parse.py         金额解析、表头映射
│   ├── mapping.py       OA 数据 → 财务字段
│   └── repair.py        校验错误 → 修正动作
├── scripts/             手动入口，不属于库
│   ├── probe_browser.py 浏览器探针（一次性）
│   └── run_task.py      按任务跑配方
│   └── run_demo.py      端到端演示（建单 + 修正 + 核验）
├── recipes/             配方：怎么做（流程）
└── tasks/               任务：做什么（数据）
```

**分层原则**：`business/` 里的函数不 import 网络、不 import 浏览器，随时可以单测；
需要 IO 的编排放在 `scripts/` 或以后的 worker 里。

## 跑

先起两个目标系统（仓库根目录）：

```powershell
python systems/oa/run.py        # 8100
python systems/fin/run.py       # 8200
```

然后在 `agent/` 目录下：

```powershell
# 跑一份任务：读 OA 单据
python -m scripts.run_task tasks/t1.json

# 端到端：OA 数据 → 财务建单 → 修正 → 核验
python -m scripts.run_demo
```

用 `python -m` 而不是 `python scripts/xxx.py`：
后者会把 `sys.path[0]` 设成 `scripts/`，`import fin.client` 会失败。

## 退出码

| 码 | 含义 | 批处理时 |
|---|---|---|
| 0 | 成功 | 继续 |
| 1 | 执行失败（断言/超时） | 重试或转人工 |
| 2 | 配置错误（缺配方/缺参数） | **不要重试** |

## 依赖

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
```
