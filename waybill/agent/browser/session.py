"""一个已登录的浏览器会话。

登录是"会话前置"，不属于任何一份业务配方：
    每份配方都写 4 步登录，改一次登录页要改 N 处；
    以后登录方式变了（验证码、扫码），所有配方都要跟着改。

分工：
    oa_login 配方     描述"怎么登录"——它可以单独替换
    OaSession         负责"登录一次，之后反复用"
    业务配方          从"已经登录"的状态开始，第一步就是业务动作

凭据只在这里过一手：不写库、不进日志、不落到磁盘。
"""

from __future__ import annotations

from playwright.async_api import Browser, Page, Playwright, async_playwright

import config
from browser.replay import load_recipe, render, replay_on


class SessionError(Exception):
    """会话级失败：登录不上、会话过期。这类错误整批任务都做不了。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class OaSession:
    """持有浏览器和一个已登录的页面。用 async with 管生命周期。"""

    def __init__(self, *, headless: bool = False) -> None:
        self._headless = headless
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self.page: Page | None = None

    async def start(self) -> OaSession:
        """打开浏览器和页面。async with 与手动调用都走这里。"""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)
        context = await self._browser.new_context()
        self.page = await context.new_page()
        return self

    async def __aenter__(self) -> OaSession:
        return await self.start()

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._browser = None
        self._playwright = None
        self.page = None

    async def login(self, username: str, password: str) -> None:
        """跑 oa_login 配方完成登录，并确认真的进去了。

        凭据只作为配方参数传入，跑完就随调用栈消失——
        不落库、不打印、不进异常信息。
        """
        if self.page is None:
            raise SessionError("SESSION_NOT_OPEN", "会话还没打开")

        recipe = load_recipe("oa_login")
        steps = render(recipe["steps"], {"username": username, "password": password})

        # 登录步骤直接复用重放器：它已经会处理超时、断言、失败码
        result = await replay_on(self.page, recipe, steps)
        if not result["ok"]:
            # 注意：reason_message 来自断言，不含凭据
            raise SessionError(
                "LOGIN_FAILED",
                f"登录失败：[{result['reason_code']}] {result['reason_message']}",
            )

    async def require_page(self) -> Page:
        if self.page is None:
            raise SessionError("SESSION_NOT_OPEN", "会话还没打开")
        return self.page


async def open_session(username: str, password: str, *, headless: bool = False) -> OaSession:
    """开一个会话并登录好。调用方负责关闭。"""
    session = await OaSession(headless=headless).start()
    try:
        await session.login(username, password)
    except Exception:
        await session.close()
        raise
    return session


def default_credentials() -> tuple[str, str]:
    """命令行调试用：从环境变量取 OA 账号。

    控制台走的是"弹窗里人手填"，不从这里取。
    """
    return (
        config.OA_USERNAME,
        config.OA_PASSWORD,
    )
