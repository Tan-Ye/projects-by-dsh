#!/usr/bin/env bash
# 一次性初始化服务器（Alibaba Cloud Linux 3，root 执行）
#
#   scp deploy/setup-server.sh root@<ip>:/tmp/
#   ssh root@<ip> 'bash /tmp/setup-server.sh'
#
# 做四件事：装依赖 → 建用户和目录 → 建虚拟环境 → 装浏览器内核。
# 不做：拉代码（release.sh 负责）、配 nginx 站点（README 里有说明）。

set -euo pipefail

APP_DIR=/opt/waybill
APP_USER=waybill

echo "== 1/5 安装系统依赖 =="
dnf install -y nginx tar rsync

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
  1. dnf module list python3 看看有没有更高版本模块
  2. 用 uv 装（推荐，不污染系统）：
       curl -LsSf https://astral.sh/uv/install.sh | sh
       uv python install 3.11
     然后重跑本脚本，并在 steps 里把 PY 指向 uv 装的位置
EOF
    exit 1
fi
echo "使用 $PY"

echo "== 2/5 创建运行用户 =="
id "$APP_USER" >/dev/null 2>&1 || useradd --system --create-home --shell /sbin/nologin "$APP_USER"
mkdir -p "$APP_DIR"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "== 3/5 虚拟环境 =="
"$PY" -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
chown -R "$APP_USER:$APP_USER" "$APP_DIR/.venv"

echo "== 4/5 浏览器内核（约 300MB，第一次会慢） =="
if [ -f "$APP_DIR/requirements.txt" ]; then
    "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"
else
    echo "还没上传代码，先跑 deploy/release.sh，再重新执行本脚本的第 4 步"
fi
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/python" -m playwright install --with-deps chromium || {
    echo "playwright install 失败。RHEL 系如果缺库，手动装：" >&2
    echo "  dnf install -y nss atk at-spi2-atk cups-libs libdrm libxkbcommon libXcomposite libXdamage libXrandr mesa-libgbm pango" >&2
    exit 1
}

echo "== 5/5 开 nginx（站点配置在 release 后手动放） =="
systemctl enable --now nginx

cat <<'DONE'

服务器初始化完成。接下来：
  1. 本地执行 ./deploy/release.sh <user>@<ip> 上传代码
  2. 服务器上配置 agent/.env 和 systems/fin/.env（参考 deploy/prod-*.env.example）
  3. 放 systemd 单元和 nginx 站点：
       cp /opt/waybill/deploy/waybill-*.service /etc/systemd/system/
       systemctl daemon-reload && systemctl enable --now waybill-oa waybill-fin waybill-agent
       cp /opt/waybill/deploy/nginx-tycode.conf /etc/nginx/conf.d/waybill.conf
       nginx -t && systemctl reload nginx
  细节见 deploy/README.md
DONE
