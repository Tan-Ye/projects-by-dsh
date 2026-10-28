"""临时探针：确认 Playwright 能驱动 OA。

不是正式代码。跑通之后这个文件就可以删掉——
它的价值是证明"程序能开浏览器"，而不是留下来复用。
"""

import asyncio

from playwright.async_api import async_playwright


async def main() -> None:
    async with async_playwright() as p:
        # headless=False：先让它看得见，出问题能判断卡在哪一步
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        await page.goto("http://127.0.0.1:8100/login")
        print("打开登录页:", page.url)

        # 用 name 属性定位：OA 是 form 表单提交，name 是最稳的锚点
        await page.locator('input[name="username"]').fill("zhangwei")
        await page.locator('input[name="password"]').fill("oa123456")
        await page.locator('button[type="submit"]').click()

        # 等地址变成 /todo —— 比等某个元素更直接地表示"登录成功了"
        await page.wait_for_url("**/todo**")
        print("登录后地址:", page.url)

        rows = page.locator("table.grid tr")
        count = await rows.count()
        print("待办表格行数（含表头）:", count)

        # 第 0 行是表头，从第 1 行开始是数据
        if count > 1:
            print("第一条:", (await rows.nth(1).inner_text()).replace("\t", " | "))

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())