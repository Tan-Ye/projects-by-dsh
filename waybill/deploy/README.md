# 部署

两份内容：**本地开发**（Windows）和**线上部署**（Alibaba Cloud Linux 3）。

---

# 一、本地开发

## 装依赖

```powershell
cd <仓库根目录>
python -m pip install -r requirements.txt
python -m playwright install chromium
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
| 控制台 | http://127.0.0.1:8300 | `admin / waybill2026`、`auditor / audit2026` |

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

控制台前端：

```powershell
cd agent\web
pnpm install
pnpm dev          # http://127.0.0.1:5174，/api 代理到 8300
```

生产构建产物由后端直接托管，服务器上不需要 Node。

---

# 二、线上部署

目标机：Alibaba Cloud Linux 3（RHEL8 兼容，systemd + dnf），域名 `tycode.xyz`。

## 拓扑

```
公网 :80  →  nginx  →  127.0.0.1:8300   控制台（API + 前端）
                 ↘   （可选）127.0.0.1:8200  财务系统

127.0.0.1:8100  OA     只给 agent 用，公网不可达
127.0.0.1:8200  财务
```

OA 和财务是"被 agent 操作的目标系统"，暴露到公网只是增加攻击面。

## 一次性初始化

```bash
# 本地
scp deploy/setup-server.sh root@<ip>:/tmp/
ssh root@<ip> 'bash /tmp/setup-server.sh'
```

脚本做四件事：装 `python3.11` + nginx → 建 `waybill` 用户和 `/opt/waybill` → 建虚拟环境 → 装浏览器内核（约 300MB）。

## 上传代码

Windows（推荐，走系统自带的 OpenSSH）：

```powershell
powershell -ExecutionPolicy Bypass -File deploy\release.ps1 -Server root@<ip>
# pnpm 不在 PATH 上时补一个：-Pnpm "C:\path\to\pnpm.cmd"
```

Linux / macOS：

```bash
./deploy/release.sh root@<ip>
```

两者都先在本地 `pnpm build` 控制台前端，再打包上传、解压、重启三个服务。
**不会覆盖**：`.env`、`*.db`、`logs/`——重复发版不会冲掉线上配置和数据。

## 配置环境变量

服务器上：

```bash
cp /opt/waybill/deploy/prod-agent.env.example /opt/waybill/agent/.env
cp /opt/waybill/deploy/prod-fin.env.example   /opt/waybill/systems/fin/.env
vi /opt/waybill/agent/.env            # 填 LLM_API_KEY、两个随机串
vi /opt/waybill/systems/fin/.env      # FIN_ADMIN_TOKEN 要和 agent 的一致

# 随机串
python3.11 -c "import secrets; print(secrets.token_urlsafe(32))"

chown waybill:waybill /opt/waybill/agent/.env /opt/waybill/systems/fin/.env
chmod 600 /opt/waybill/agent/.env /opt/waybill/systems/fin/.env
```

**生产必改的三项**（忘改时服务启动会在日志里喊）：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `CONSOLE_SECRET` | `dev-only-secret-change-me` | 控制台会话签名 |
| 控制台账号口令 | `waybill2026` / `audit2026` | 改 `agent/config.py` 或后续接环境变量 |
| `FIN_ADMIN_TOKEN` | `dev-admin-token` | 评测旁路接口 |

## systemd

```bash
cp /opt/waybill/deploy/waybill-*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now waybill-oa waybill-fin waybill-agent
systemctl status waybill-agent --no-pager
journalctl -u waybill-agent -f
```

## nginx

```bash
cp /opt/waybill/deploy/nginx-tycode.conf /etc/nginx/conf.d/waybill.conf
nginx -t && systemctl reload nginx
```

DNS 把 `tycode.xyz` 的 A 记录指到服务器 IP，之后 `http://tycode.xyz` 就能打开控制台。

## HTTPS（域名解析 + 备案完成之后）

```bash
dnf install -y certbot python3-certbot-nginx
certbot --nginx -d tycode.xyz -d www.tycode.xyz
```

拿到证书后把 `agent/.env` 里的 `COOKIE_SECURE` 改成 `1`，重启 agent：

```bash
sed -i 's/^COOKIE_SECURE=0/COOKIE_SECURE=1/' /opt/waybill/agent/.env
systemctl restart waybill-agent
```

## 备份

SQLite 单文件，用官方在线备份命令（不要直接 cp，可能拷到半个事务）：

```bash
mkdir -p /opt/waybill/data/backup
sqlite3 /opt/waybill/agent/agent.db ".backup '/opt/waybill/data/backup/agent-$(date +%F).db'"
```

`crontab -e` 加一条每日备份，保留 7 天。

## 常见问题

| 现象 | 原因 |
|---|---|
| 控制台 502 | agent 没起来：`journalctl -u waybill-agent -n 50` |
| 批次一启动就失败，日志 `BROWSER_UNAVAILABLE` | 浏览器内核没装：`sudo -u waybill /opt/waybill/.venv/bin/python -m playwright install --with-deps chromium` |
| 批次能启动但登录失败 | 先确认 OA 在跑：`curl -I http://127.0.0.1:8100/login` |
| 页面能开，接口 404 | nginx 没配 `/api/`，或 `BIND_HOST` 被改成了 0.0.0.0 但端口没放行 |
| 登录后立刻被踢回登录页 | `COOKIE_SECURE=1` 但还在用 HTTP |

## 已知限制

**人工闸门的「重跑」在生产上不会真正执行。** 它只把任务状态改回 `pending`，
需要有人跑 `python -m scripts.worker` 来消费；而 worker 需要 OA 账号，
这和"账号由人当场填"的设计冲突。

生产上的正确做法是：**用「批次」重扫一遍**——已经建过单的会被跳过，
只补没处理完的。等单号级重跑做完（弹窗填账号起一个只含该单号的批次）再改。
