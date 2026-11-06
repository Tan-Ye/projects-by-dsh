#!/usr/bin/env bash
# 本地发版：构建前端 → 打包 → 上传 → 重启服务
#
#   ./deploy/release.sh root@<服务器IP>
#
# 不上传：.env（服务器自己保存）、*.db（线上数据）、logs、node_modules、.git
# 所以重复发版不会覆盖线上配置和数据。

set -euo pipefail

HOST=${1:-}
if [ -z "$HOST" ]; then
    echo "用法: ./deploy/release.sh <user>@<host>" >&2
    exit 1
fi

ROOT=$(cd "$(dirname "$0")/.." && pwd)
APP_DIR=/opt/waybill

echo "== 1/4 构建前端（控制台 + 财务） =="
build_frontend() {
    local dir="$ROOT/$1"
    if [ ! -d "$dir/node_modules" ]; then
        echo "$1/node_modules 不存在，先在该目录 pnpm install" >&2
        exit 1
    fi
    echo "  构建 $1"
    (cd "$dir" && pnpm build)
}

# 两个前端都要构建：少构建一个，线上就是"前端还没构建"的占位页
build_frontend agent/web
build_frontend systems/fin/web

echo "== 2/4 打包 =="
TARBALL=/tmp/waybill-$(date +%Y%m%d-%H%M%S).tgz
tar -czf "$TARBALL" -C "$ROOT" \
    --exclude='.git' \
    --exclude='node_modules' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.db' \
    --exclude='*.db-wal' \
    --exclude='*.db-shm' \
    --exclude='agent/.env' \
    --exclude='systems/fin/.env' \
    --exclude='agent/logs' \
    .
echo "包大小: $(du -h "$TARBALL" | cut -f1)"

echo "== 3/4 上传 =="
scp "$TARBALL" "$HOST:/tmp/waybill-release.tgz"

echo "== 4/4 远端解压并重启 =="
ssh "$HOST" "APP_DIR=$APP_DIR bash -s" <<'REMOTE'
set -euo pipefail
mkdir -p "$APP_DIR"
tar -xzf /tmp/waybill-release.tgz -C "$APP_DIR"
# 依赖可能随代码变化：每次装一遍，已满足的会很快跳过
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
chown -R waybill:waybill "$APP_DIR"
systemctl restart waybill-oa waybill-fin waybill-agent
sleep 2
systemctl --no-pager --lines=0 is-active waybill-oa waybill-fin waybill-agent
curl -fsS http://127.0.0.1:8300/health >/dev/null && echo "agent 健康检查通过"
curl -fsS http://127.0.0.1:8200/health >/dev/null && echo "财务健康检查通过"
REMOTE

echo "完成：$(basename "$TARBALL")"
