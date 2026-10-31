#!/usr/bin/env bash
# 第二步：装 Chromium（只需一次，约 300MB）。代码上传后执行。
#
#   scp deploy/setup-browser.sh root@<ip>:/tmp/
#   ssh root@<ip> 'bash /tmp/setup-browser.sh'
#
# 为什么要单独一个脚本：
#   - 系统库要用 root 装（dnf）
#   - 浏览器本体要装到共享目录，由 waybill 用户读写
#   默认装到 ~/.cache 的话，root 装的浏览器 waybill 用不了。

set -euo pipefail

APP_DIR=/opt/waybill
APP_USER=waybill
BROWSERS="$APP_DIR/.pw-browsers"

if [ ! -x "$APP_DIR/.venv/bin/python" ]; then
    echo "虚拟环境还没建：先跑 setup-server.sh" >&2
    exit 1
fi
if ! "$APP_DIR/.venv/bin/python" -c "import playwright" 2>/dev/null; then
    echo "playwright 还没装：先本地 release.ps1 上传代码并装依赖" >&2
    exit 1
fi

echo "== 1/3 系统库（浏览器渲染依赖） =="
"$APP_DIR/.venv/bin/python" -m playwright install-deps chromium || {
    echo "install-deps 失败，手动补：" >&2
    echo "  dnf install -y nss atk at-spi2-atk cups-libs libdrm libxkbcommon \
libXcomposite libXdamage libXrandr mesa-libgbm pango" >&2
    exit 1
}

echo "== 2/3 浏览器本体（装到 $BROWSERS） =="
mkdir -p "$BROWSERS"
chown -R "$APP_USER:$APP_USER" "$BROWSERS"
sudo -u "$APP_USER" env PLAYWRIGHT_BROWSERS_PATH="$BROWSERS" \
    "$APP_DIR/.venv/bin/python" -m playwright install chromium

echo "== 3/3 验证 =="
sudo -u "$APP_USER" env PLAYWRIGHT_BROWSERS_PATH="$BROWSERS" \
    "$APP_DIR/.venv/bin/python" - <<'PY'
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_content("<h1>ok</h1>")
    print("Chromium 可用，页面标题占位测试通过")
    browser.close()
PY

echo "完成。systemd 单元里已经配好 PLAYWRIGHT_BROWSERS_PATH。"
