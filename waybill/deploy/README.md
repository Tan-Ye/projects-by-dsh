# 本地一键启动

## 先装依赖

```powershell
cd <仓库根目录>
python -m pip install -r requirements.txt
```

## 启动

```powershell
powershell -ExecutionPolicy Bypass -File deploy\start_all.ps1
```

脚本会自动找可用的解释器（优先 `py`，其次 `python`）。

| 系统 | 地址 | 账号 |
|---|---|---|
| OA | http://127.0.0.1:8100 | `zhangwei / oa123456` |
| 财务 | http://127.0.0.1:8200 | `maker / maker123`（制单）、`checker / checker123`（复核） |

## 停止

```powershell
powershell -ExecutionPolicy Bypass -File deploy\stop_all.ps1
```

## 前端开发

```powershell
cd systems\fin\web
pnpm install
pnpm dev          # http://127.0.0.1:5173，/api 代理到 8200
```

生产构建是 `pnpm build`，产物 `web/dist` 由 FastAPI 直接托管，不需要单独跑 Node。
