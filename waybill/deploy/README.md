# 部署

两份内容：**本地开发**（Windows）和**线上部署**（阿里云香港 + Alibaba Cloud Linux 3）。

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
cd systems\fin\web ; pnpm install ; pnpm dev   # 5173，/api 代理到 8200
cd agent\web      ; pnpm install ; pnpm dev   # 5174，/api 代理到 8300
```

生产构建产物由后端直接托管，服务器上不需要 Node。

---

# 二、线上部署

目标机：阿里云香港轻量/ECS，Alibaba Cloud Linux 3，域名 `tycode.xyz`。
香港机房**不需要备案**，80/443 可直接用。

## 拓扑

```
公网 :80/:443 → nginx → 127.0.0.1:8300   控制台（API + 前端）

127.0.0.1:8100  OA      只给 agent 用，公网不可达
127.0.0.1:8200  财务
```

OA 和财务是"被 agent 操作的目标系统"，不对外是刻意的。

## 步骤 0：把服务器变成能连的

在阿里云控制台完成三件事：

1. **设置登录凭据**：实例 → 重置实例密码（或绑定 SSH 密钥对）
2. **安全组放行**：22（SSH）、80、443
3. **DNS 解析**：`tycode.xyz` 和 `www.tycode.xyz` 各加一条 A 记录指向公网 IP

本地验证（Windows 自带 OpenSSH）：

```powershell
ssh root@<公网IP>
# 第一次会问 yes/no，输 yes，再输密码
```

## 步骤 1：基础环境

```powershell
scp deploy\setup-server.sh root@<IP>:/tmp/
ssh root@<IP> "bash /tmp/setup-server.sh"
```

装 Python 3.11、nginx、建 `waybill` 用户、建虚拟环境。

## 步骤 2：上传代码（顺带装 Python 依赖）

```powershell
powershell -ExecutionPolicy Bypass -File deploy\release.ps1 -Server root@<IP>
```

本地先 `pnpm build` 控制台前端，再打包上传、解压、`pip install`、重启服务。
**不会覆盖** `.env`、`*.db`、`logs/`——重复发版不冲掉线上配置和数据。

> pnpm 不在 PATH 上时补 `-Pnpm "完整路径\pnpm.cmd"`。

## 步骤 3：浏览器内核（只需一次）

```powershell
scp deploy\setup-browser.sh root@<IP>:/tmp/
ssh root@<IP> "bash /tmp/setup-browser.sh"
```

系统库用 root 装，浏览器本体装到 `/opt/waybill/.pw-browsers`（共享，`waybill` 可读写）。
默认装到 `~/.cache` 的话，root 装的浏览器 `waybill` 用不了——这是最容易踩的坑。

## 步骤 4：环境变量

```bash
cd /opt/waybill
cp deploy/prod-agent.env.example agent/.env
cp deploy/prod-fin.env.example   systems/fin/.env
python3.11 -c "import secrets; print(secrets.token_urlsafe(32))"   # 生成两串随机值
vi agent/.env            # 填 LLM_API_KEY、CONSOLE_SECRET、FIN_ADMIN_TOKEN
vi systems/fin/.env      # FIN_ADMIN_TOKEN 必须和 agent 里的一致
chown waybill:waybill agent/.env systems/fin/.env
chmod 600 agent/.env systems/fin/.env
```

生产必改三项（忘改时启动日志会喊）：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `CONSOLE_SECRET` | `dev-only-secret-change-me` | 控制台会话签名 |
| 控制台口令 | `waybill2026` / `audit2026` | 改 `agent/config.py` 的 `CONSOLE_USERS` |
| `FIN_ADMIN_TOKEN` | `dev-admin-token` | 评测旁路接口 |

## 步骤 5：systemd 与 nginx

```bash
cp /opt/waybill/deploy/waybill-*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now waybill-oa waybill-fin waybill-agent

cp /opt/waybill/deploy/nginx-tycode.conf /etc/nginx/conf.d/waybill.conf
nginx -t && systemctl reload nginx
```

此时 `http://tycode.xyz` 应该能打开控制台。

## 步骤 6：HTTPS

香港机器不需要备案，DNS 生效后直接签证书：

```bash
dnf install -y certbot python3-certbot-nginx
certbot --nginx -d tycode.xyz -d www.tycode.xyz
```

拿到证书后打开 cookie 的 Secure 标记：

```bash
sed -i 's/^COOKIE_SECURE=0/COOKIE_SECURE=1/' /opt/waybill/agent/.env
systemctl restart waybill-agent
```

## 备份

SQLite 单文件，用官方在线备份（直接 `cp` 可能拷到半个事务）：

```bash
mkdir -p /opt/waybill/data/backup
sqlite3 /opt/waybill/agent/agent.db ".backup '/opt/waybill/data/backup/agent-$(date +%F).db'"
```

`crontab -e` 加一条每日备份，保留 7 天：

```
0 3 * * * sqlite3 /opt/waybill/agent/agent.db ".backup '/opt/waybill/data/backup/agent-$(date +\%F).db'" && find /opt/waybill/data/backup -name 'agent-*.db' -mtime +7 -delete
```

## 日常发布

改完代码，本地一条命令：

```powershell
powershell -ExecutionPolicy Bypass -File deploy\release.ps1 -Server root@<IP>
```

回滚：`git checkout <上一个提交>` 后重新发版；数据库不回滚，但 `batch_items` / `runs` 都留着记录。

## 常见问题

| 现象 | 原因 |
|---|---|
| 控制台 502 | agent 没起来：`journalctl -u waybill-agent -n 50` |
| 批次一启动就失败，日志 `BROWSER_UNAVAILABLE` | 浏览器没装：执行步骤 3 |
| 批次能启动但登录失败 | 确认 OA 在跑：`curl -I http://127.0.0.1:8100/login` |
| 页面能开，接口 404 | nginx 没配 `/api/`，或 `BIND_HOST` 改成了 0.0.0.0 但端口没放行 |
| 登录后立刻被踢回登录页 | `COOKIE_SECURE=1` 但还在用 HTTP |
| 打开页面提示"前端还没构建" | 发版时 `pnpm build` 失败，或包没传上去 |

## 已知限制

**人工闸门的「重跑」在生产上不会真正执行。** 它只把任务状态改回 `pending`，
需要有人跑 `python -m scripts.worker` 消费；而 worker 需要 OA 账号，
这和"账号由人当场填"的设计冲突。

生产上的替代做法：**用「批次」重扫**——已建过单的会被跳过，只补没处理的。
彻底修法是让重跑也能填账号、起一个只含该单号的批次，属于后续迭代。
