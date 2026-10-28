"""OA 仿真系统的冒烟测试。

    python tools/smoke_oa.py [base_url]

不需要任何第三方库，直接跑 urllib。检查的是"页面里到底有没有那些该有的东西"，
和以后 Playwright 的 E2E 是两回事——这里只保证 HTML 层没写错。
"""

from __future__ import annotations

import http.cookiejar
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8100"

passed = failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    if ok:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def make_opener(follow: bool = True):
    jar = http.cookiejar.CookieJar()
    handlers = [urllib.request.HTTPCookieProcessor(jar)]
    if not follow:
        handlers.append(NoRedirect())
    return urllib.request.build_opener(*handlers), jar


def fetch(opener, path: str, data: dict | None = None):
    url = BASE + path
    body = urllib.parse.urlencode(data).encode() if data else None
    try:
        with opener.open(url, body, timeout=10) as r:
            return r.status, r.read().decode("utf-8"), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8"), dict(e.headers)


def main() -> int:
    print(f"smoke test -> {BASE}")

    # 1. 未登录应当被踢回登录页
    anon, _ = make_opener(follow=False)
    status, _, headers = fetch(anon, "/todo")
    check("未登录访问 /todo 返回 3xx", 300 <= status < 400, f"status={status}")
    check("重定向到登录页并带上 redirect",
          headers.get("Location", "").startswith("/login?redirect="), headers.get("Location", ""))

    # 2. 登录
    status, html, _ = fetch(anon, "/login")
    check("GET /login 直接返回登录页", status == 200 and 'name="password"' in html, f"status={status}")
    status, _, headers = fetch(anon, "/login/")
    check("结尾斜杠 301 到 /login", status == 301 and headers.get("Location") == "/login",
          f"{status} {headers.get('Location')}")

    sess, jar = make_opener()
    status, _, _ = fetch(sess, "/login", {"username": "zhangwei", "password": "oa123456", "redirect": "/todo"})
    check("登录返回 200（跟随重定向后）", status == 200, f"status={status}")
    check("拿到会话 cookie", any(c.name == "oa_session" for c in jar), str([c.name for c in jar]))

    bad, _ = make_opener()
    status, _, _ = fetch(bad, "/login", {"username": "zhangwei", "password": "wrong"})
    check("错误密码返回 401", status == 401, f"status={status}")

    # 3. 待办列表与分页
    status, html, _ = fetch(sess, "/todo")
    check("待办页 200", status == 200)
    check("显示总条数 18", "共 18 条" in html)
    check("第 1 页含 BX-2024-1019", "BX-2024-1019" in html)
    check("第 1 页不含 BX-2024-0912", "BX-2024-0912" not in html)

    status, html, _ = fetch(sess, "/todo?page=2")
    check("第 2 页含 BX-2024-0912", "BX-2024-0912" in html)
    check("分页器显示 2/2", "第 2 / 2 页" in html)

    # 4. 单据头
    status, html, _ = fetch(sess, "/doc/BX-2024-0912")
    check("单据页 200", status == 200)
    check("内嵌 iframe 指向明细", 'src="/doc/BX-2024-0912/detail"' in html)
    check("显示合计金额", "￥128.60元" in html)
    check("显示附单据数", "1 张" in html)
    check("单据页有跳到明细页的入口",
          'class="linkbtn" href="/doc/BX-2024-0912/detail"' in html)

    # 5. iframe 明细页
    status, html, _ = fetch(sess, "/doc/BX-2024-0912/detail")
    check("明细页 200", status == 200)
    check("金额带货币符号和中文后缀", "￥128.60元" in html)
    check("附件文件名只出现在 title 属性里", 'title="出租车发票_0910.pdf"' in html)
    check("没有 data-testid", "data-testid" not in html)
    check("明细页有返回单据的链接", 'href="/doc/BX-2024-0912" target="_top"' in html)

    # 5b. 不存在的路由走统一错误页
    status, html, _ = fetch(sess, "/nope")
    check("未知路由返回 404 且是可读页面", status == 404 and "页面不存在" in html, f"status={status}")

    # 6. T4 的不一致：3 个附件、2 条明细
    status, body, _ = fetch(sess, "/api/state/BX-2024-1005")
    check("T4 明细行附件数合计为 2", '"line_attachment_sum": 2' in body)
    check("T4 实际附件为 3", '"attachment_total": 3' in body)

    # 7. 漂移：v2 列顺序变化，v3 明细分页
    status, html, _ = fetch(sess, "/doc/BX-2024-0930/detail?ui=v2")
    check("v2 页面 200", status == 200)
    check("v2 金额列排在发生日期之前",
          html.find("<th>金额</th>") < html.find("<th>发生日期</th>"),
          f"金额@{html.find('<th>金额</th>')} 日期@{html.find('<th>发生日期</th>')}")

    status, html, _ = fetch(sess, "/doc/BX-2024-0930/detail?ui=v3")
    check("v3 页面 200", status == 200)
    check("v3 明细分页 1/2", "第 1 / 2 页" in html)
    status, html, _ = fetch(sess, "/doc/BX-2024-0930/detail?p=2")
    check("v3 第 2 页含最后一行", "北京往返高铁票" in html)

    # 8. 静态资源
    status, css, _ = fetch(sess, "/static/oa.css")
    check("样式表可访问", status == 200 and "topbar" in css)

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
