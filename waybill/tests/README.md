# 测试

后端用标准库 `unittest`，前端用 Node 自带的 `node:test`，两套都不装框架。

## 后端

```powershell
# 仓库根目录，先装依赖
python -m pip install -r requirements.txt

python -m unittest discover -s tests -t tests -p "test_*.py" -v
```

| 文件 | 覆盖 | 是否起服务 |
|---|---|---|
| `test_fin_units.py` | 种子数据、密码哈希、查询函数、校验规则、写入与分页 | 否，直接调 `app.db` / `app.validation` |
| `test_fin_api.py` | 登录、鉴权、meta、凭证建/查/改、两步审批、角色限制、错误形状、token 过期 | 是，每个测试类起一个真的 uvicorn |

## 前端

```powershell
cd systems/fin/web
pnpm test
```

测试在 `systems/fin/web/tests/`，只测纯逻辑，**不做组件测试**——组件行为靠浏览器和 agent 验证，DOM 快照那种测试维护成本高、收益低。

| 文件 | 覆盖 |
|---|---|
| `money.test.ts` | 元↔分换算、浮点陷阱、非法输入、往返精度 |
| `http.test.ts` | token 注入、查询参数拼接、错误翻译、401 清会话、非 JSON 响应兜底 |
| `filters.test.ts` | 筛选条件序列化、脏数据回退、按角色分 key |
| `format.test.ts` | 状态文案与颜色、未知状态、时间格式化 |

**注意 `--test-isolation=none`**：默认模式下 node 会为每个测试文件起子进程，这台机器的沙箱禁止带管道的子进程（`spawn EPERM`）。关掉隔离后所有文件在同一个进程里跑，也更快。

## 几个约定

- **临时数据库放在 `tests/.tmp/`**，不用系统临时目录——这台机器的沙箱不允许在 `%TEMP%` 下建文件。用完即删，目录可留空。
- 接口测试把 `FIN_VALIDATE_DELAY_MS` 调成 10ms，否则每个保存用例要真等 800ms。
- token 过期单独起一个 `TOKEN_TTL=1` 的服务，只为一个用例多花 1.3 秒。
- 每个用例用独立数据库文件，互不影响，可并行跑。

## OA 的测试

OA 是零依赖的标准库服务，测试在 `tools/smoke_oa.py`：

```powershell
python systems/oa/run.py --port 8110
python tools/smoke_oa.py http://127.0.0.1:8110
```

覆盖 32 项：登录、分页、iframe 明细、附件标题、漂移 v2/v3、会话过期。
