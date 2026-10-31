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

echo "== 1/4 构建控制台前端 =="
if [ -d "$ROOT/agent/web/node_modules" ]; then
    (cd "$ROOT/agent/web" && pnpm build)
else
    echo "agent/web/node_modules 不存在，先 pnpm install" >&2
    exit 1
fi

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
chown -R waybill:waybill "$APP_DIR"
systemctl restart waybill-oa waybill-fin waybill-agent
sleep 2
systemctl --no-pager --lines=0 status waybill-oa waybill-fin waybill-agent || true
curl -fsS http://127.0.0.1:8300/health >/dev/null && echo "agent 健康检查通过"
REMOTE

echo "完成：$(basename "$TARBALL")"
