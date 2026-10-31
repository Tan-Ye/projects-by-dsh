#!/usr/bin/env bash
# 第一步：服务器基础环境（Alibaba Cloud Linux 3，root 执行）
#
#   scp deploy/setup-server.sh root@<ip>:/tmp/
#   ssh root@<ip> 'bash /tmp/setup-server.sh'
#
# 只装"和代码无关"的东西：Python、nginx、运行用户、虚拟环境目录。
# 代码里的依赖在 release 之后由 deploy/setup-browser.sh 和 release 脚本装。

set -euo pipefail

APP_DIR=/opt/waybill
APP_USER=waybill

echo "== 1/4 安装系统工具 =="
dnf install -y nginx tar rsync

echo "== 2/4 找到 3.10+ 的 Python =="
# 代码用到 3.10+ 的语法（match、X | None），3.9 及以下跑不起来
PY=""
for candidate in python3.12 python3.11 python3.10; do
    if dnf install -y "$candidate" "$candidate-pip" 2>/dev/null; then
        PY="$candidate"
        break
    fi
done
if [ -z "$PY" ]; then
    cat >&2 <<'EOF'
源里没有 3.10+ 的 Python。两种办法：
  1. dnf module list python3   看看有没有更高版本模块
  2. 用 uv 装（不污染系统）：
       curl -LsSf https://astral.sh/uv/install.sh | sh
       uv python install 3.11
     然后把 venv 建在 /opt/waybill/.venv（见脚本后半段）
EOF
    exit 1
fi
echo "使用 $PY"

echo "== 3/4 运行用户与目录 =="
id "$APP_USER" >/dev/null 2>&1 || useradd --system --create-home --shell /sbin/nologin "$APP_USER"
mkdir -p "$APP_DIR"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "== 4/4 虚拟环境 =="
if [ ! -x "$APP_DIR/.venv/bin/python" ]; then
    "$PY" -m venv "$APP_DIR/.venv"
fi
"$APP_DIR/.venv/bin/pip" install --upgrade pip
chown -R "$APP_USER:$APP_USER" "$APP_DIR/.venv"

systemctl enable --now nginx

cat <<'DONE'

基础环境就绪。接下来：
  1. 本地发版（会顺带装 Python 依赖）：deploy\release.ps1 -Server root@<ip>
  2. 装浏览器内核（只需一次）：scp deploy/setup-browser.sh root@<ip>:/tmp/
     ssh root@<ip> 'bash /tmp/setup-browser.sh'
  3. 配置 .env、systemd 单元、nginx 站点（见 deploy/README.md）
DONE
