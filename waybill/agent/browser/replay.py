"""配方重放器 v0。

读一份 JSON 配方，按 seq 顺序执行，每步打印结果。
只支持 6 种动作——够跑通登录。动作类型以后会长出来，
到那时候再把"执行"抽成独立模块，现在不提前抽象。
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypedDict

import config
from business.parse import normalize_label, rows_to_dicts

from playwright.async_api import (
    Locator,
    Page,
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
)

class StepResult(TypedDict):
    """一步的执行事实，落库进 steps 表。"""

    seq: int
    intent: str
    action: str
    outcome: str                     # ok / failed
    reason_code: str | None
    reason_message: str | None
    target_path: str | None          # 失败时指出是哪个 target（action / asserts[i]）
    duration_ms: int


class RepairRecord(TypedDict):
    """一次自愈：修了哪一步、原来的 target 换成什么。"""

    seq: int
    where: str | None
    old_target: dict[str, Any] | None
    new_target: dict[str, Any] | None
    confidence: float
    rationale: str
    model: str


class RunResult(TypedDict):
    """一次重放的结果。

    执行器只产事实，不产结论——"失败了要不要重试""要不要转人工"
    由上层根据 reason_code 决定。
    """

    ok: bool
    outputs: dict[str, Any]          # 配方里 "as": xxx 收集到的数据
    steps: list[StepResult]          # 每一步的事实，用于留痕
    fixes: list[RepairRecord]        # 成功修好的（重试通过）
    failed_repair: RepairRecord | None   # 试过但没修好的
    failed_step: int | None
    failed_where: str | None
    reason_code: str | None
    reason_message: str | None


# 默认 5 秒。Playwright 默认 30 秒，失败时你要干等半分钟才知道出问题
DEFAULT_TIMEOUT_MS = 5_000

# 只有"结构漂移"类失败才值得重新定位。
# 断言内容不符、金额对不上这些，模型改 target 也解决不了。
LOCATE_ERRORS = frozenset(
    {
        "STEP_TIMEOUT",
        "EXTRACT_NO_TABLE",
        "EXTRACT_NO_HEADER",
        "EXTRACT_EMPTY_FORM",
        "ASSERT_NOT_VISIBLE",
        "ASSERT_NO_TEXT",
    }
)


class StepFailed(Exception):
    """一步失败。code 是原因码，where 指出是哪个 target 挂了。"""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        where: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.where = where


# 自愈钩子：拿到页面、失败的步骤、失败原因，返回修好的步骤（或 None 表示修不了）。
# 返回值一律不信任——调用方会拿它重跑这一步，跑通才算修好。
class RepairDecision(TypedDict):
    """修复建议。step 是改好 target 的步骤，其余字段只用于留痕。"""

    step: dict[str, Any]
    confidence: float
    rationale: str
    model: str


RepairHook = Callable[[Page, dict[str, Any], StepFailed], Awaitable[RepairDecision | None]]


PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def render(node: Any, inputs: dict[str, str]) -> Any:
    """递归替换配方里的 {{参数}}。

    三种容器都要处理：字符串里的占位、字典的值、列表的元素。
    缺参数直接抛错——静默变成空串会让后面的失败发生在很远的地方。
    """
    match node:
        case str():

            def substitute(match: re.Match[str]) -> str:
                key = match.group(1)
                if key not in inputs:
                    raise StepFailed("MISSING_INPUT", f"缺少参数 {key}")
                return str(inputs[key])

            return PLACEHOLDER.sub(substitute, node)
        case dict():
            return {key: render(value, inputs) for key, value in node.items()}
        case list():
            return [render(item, inputs) for item in node]
        case _:
            return node


def load_recipe(recipe_name: str) -> dict[str, Any]:
    """按名字加载配方。

    文件名和配方名必须一致：否则"按名字查配方"就有歧义。
    队列里的任务只存配方名，所以这个函数要能脱离任务文件单独用。
    """
    recipe_path = config.RECIPE_DIR / f"{recipe_name}.json"
    if not recipe_path.is_file():
        raise StepFailed("RECIPE_NOT_FOUND", f"配方文件 {recipe_path.name} 不存在")

    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    if recipe.get("name") != recipe_path.stem:
        raise StepFailed(
            "RECIPE_NAME_MISMATCH",
            f"配方名 {recipe.get('name')!r} 与文件名 {recipe_path.stem!r} 不一致",
        )
    return recipe


def load_task_and_recipe(
    task_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """任务文件 → 配方 + 渲染好的步骤。

    所有配置错误都在这里暴露，全部发生在开浏览器之前。
    """
    if not task_path.is_file():
        raise StepFailed("TASK_NOT_FOUND", f"任务文件 {task_path} 不存在")
    task = json.loads(task_path.read_text(encoding="utf-8"))

    recipe_name = task.get("recipe")
    if not recipe_name:
        raise StepFailed("MISSING_RECIPE", "任务文件中缺少 recipe 字段")

    recipe = load_recipe(recipe_name)

    inputs = task.get("inputs", {})
    missing = [key for key in recipe.get("requires", []) if key not in inputs]
    if missing:
        raise StepFailed("MISSING_INPUT", f"缺少参数: {', '.join(missing)}")
    return recipe, render(recipe["steps"], inputs)


def locate(page: Page, target: dict[str, Any]) -> Locator:
    """
    把配方里的 target 翻译成 Playwright 的 locator。

    支持多种定位方式，是为了以后能做"策略降级"：
    一种找法失效时，换下一种继续试。
    """
    by = target["by"]
    value = target["value"]

    match by:
        case "css":
            return page.locator(value)
        case "name":
            return page.locator(f'[name="{value}"]')
        case "text":
            return page.get_by_text(value, exact=True)
        case "role":
            return page.get_by_role(value)
        case _:
            raise StepFailed("TARGET_UNSUPPORTED", f"不支持的定位方式: {by}")


async def run_action(page: Page, step: dict[str, Any], base_url: str) -> Any:
    """执行一步。返回值会打印出来，便于观察。"""
    action = step["action"]

    match action:
        case "goto":
            await page.goto(base_url + step["url"])
        case "fill":
            await locate(page, step["target"]).fill(step["value"])
        case "click":
            await locate(page, step["target"]).click()
        case "expect_url":
            await page.wait_for_url(step["pattern"], timeout=DEFAULT_TIMEOUT_MS)
        case "count":
            return await locate(page, step["target"]).count()
        case "extract_table":
            # 明细在 iframe 里：先拿 FrameLocator 才进得去
            scope = page.frame_locator("iframe") if step.get("in_frame") else page
            table = scope.locator(step["target"]["value"])

            # count() / all_inner_texts() 都不会等待元素出现。
            # 不显式等第一行的话，"没找到表"会静默返回空列表，
            # 看起来像"这张单据没有明细"——两种失败的排查方向完全不同。
            try:
                await table.locator("tr").first.wait_for(timeout=DEFAULT_TIMEOUT_MS)
            except PlaywrightTimeoutError as exc:
                raise StepFailed(
                    "EXTRACT_NO_TABLE",
                    f"没找到表格 {step['target']['value']}（in_frame={step.get('in_frame', False)}）",
                ) from exc

            headers = [
                text.strip()
                for text in await table.locator("tr")
                .first.locator("th")
                .all_inner_texts()
            ]
            if not headers:
                # 有表但没表头，按列名取值就无从谈起
                raise StepFailed("EXTRACT_NO_HEADER", "表格没有表头，无法按列名取值")

            row_count = await table.locator("tr").count()

            rows: list[list[str]] = []
            for index in range(1, row_count):
                cells = (
                    await table.locator("tr").nth(index).locator("td").all_inner_texts()
                )
                if cells:
                    rows.append([cell.strip() for cell in cells])

            return rows_to_dicts(headers, rows)
        case "extract_kv_table":
            # 标签-值表：单据头这种"一行里 标签,值,标签,值"的结构。
            # 和 extract_table 用同一套定位逻辑：表在哪由配方声明，动作不假设。
            scope = page.frame_locator("iframe") if step.get("in_frame") else page
            table = scope.locator(step["target"]["value"]).first

            try:
                await table.locator("tr").first.wait_for(timeout=DEFAULT_TIMEOUT_MS)
            except PlaywrightTimeoutError as exc:
                raise StepFailed(
                    "EXTRACT_NO_TABLE",
                    f"没找到表格 {step['target']['value']}（in_frame={step.get('in_frame', False)}）",
                ) from exc

            row_count = await table.locator("tr").count()

            pairs: dict[str, str] = {}
            for index in range(row_count):
                cells = [
                    cell.strip()
                    for cell in await table.locator("tr")
                    .nth(index)
                    .locator("td")
                    .all_inner_texts()
                ]
                # 一行可能是 2 段（标签+值）或 4 段（标签+值+标签+值）
                for pos in range(0, len(cells) - 1, 2):
                    key = normalize_label(cells[pos])
                    if key:
                        pairs[key] = cells[pos + 1]

            if not pairs:
                raise StepFailed("EXTRACT_EMPTY_FORM", "单据头没有解析出任何字段")

            return pairs
        case "extract_text":
            # 取一段文本：标题里的"共 N 条"、分页条的"第 X / Y 页"都靠它
            scope = page.frame_locator("iframe") if step.get("in_frame") else page
            locator = scope.locator(step["target"]["value"]).first
            try:
                return (await locator.inner_text(timeout=DEFAULT_TIMEOUT_MS)).strip()
            except PlaywrightTimeoutError as exc:
                raise StepFailed(
                    "EXTRACT_NO_TEXT",
                    f"没找到文本元素 {step['target']['value']}",
                ) from exc
        case "expect_absent":
            # 断言"这个东西不该存在"。用在抽取之后：
            # 出现了分页控件，说明刚才只读了第一页，数据是不完整的。
            scope = page.frame_locator("iframe") if step.get("in_frame") else page
            locator = scope.locator(step["target"]["value"])

            if await locator.count():
                detail = (await locator.first.inner_text()).strip().replace("\n", " ")
                raise StepFailed(
                    "EXTRACT_TRUNCATED",
                    f"出现了分页控件（{detail[:60]}），只读到第一页，数据不完整",
                )
            return None
        case _:
            raise StepFailed("ACTION_UNSUPPORTED", f"不支持的动作: {action}")
    return None


async def run_assert(page: Page, spec: dict[str, Any]) -> None:
    """跑一条断言。不满足就抛 StepFailed，并带上原因码。"""
    kind = spec["kind"]
    timeout = spec.get("timeout", DEFAULT_TIMEOUT_MS)

    match kind:
        case "visible":
            try:
                await locate(page, spec["target"]).wait_for(
                    state="visible", timeout=timeout
                )
            except PlaywrightTimeoutError as exc:
                raise StepFailed("ASSERT_NOT_VISIBLE", "该出现的元素没有出现") from exc
        case "text":
            try:
                actual = await locate(page, spec["target"]).inner_text(timeout=timeout)
            except PlaywrightTimeoutError as exc:
                raise StepFailed("ASSERT_NO_TEXT", "找不到承载文本的元素") from exc
            if spec["contains"] not in actual:
                raise StepFailed(
                    "ASSERT_TEXT_MISMATCH",
                    f"期望包含 {spec['contains']!r}, 实际{actual.strip()!r}",
                )
        case "count":
            actual_count = await locate(page, spec["target"]).count()
            if actual_count != spec["equals"]:
                raise StepFailed(
                    "ASSERT_COUNT_MISMATCH",
                    f"期望 {spec['equals']}行，实际{actual_count}行",
                )
        case _:
            raise StepFailed("ASSERT_UNSUPPORTED", f"不支持的断言类型: {kind}")


def _step_result(
    step: dict[str, Any],
    outcome: str,
    failure: StepFailed | None,
    started: float,
) -> StepResult:
    """把一步的执行情况收成一条记录，供上层落库。"""
    return StepResult(
        seq=step["seq"],
        intent=step["intent"],
        action=step["action"],
        outcome=outcome,
        reason_code=failure.code if failure else None,
        reason_message=failure.message if failure else None,
        target_path=failure.where if failure else None,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )


async def _run_step(page: Page, step: dict[str, Any], base_url: str) -> Any:
    """执行一步的动作 + 全部断言。

    失败的 where 要指到具体 target：
    动作失败归到 action.target，第 i 条断言失败归到 asserts[i].target。
    自愈靠这个路径知道该修哪一处。
    """
    try:
        result = await run_action(page, step, base_url)
    except StepFailed as exc:
        if exc.where is None:
            raise StepFailed(exc.code, exc.message, where="action.target") from exc
        raise

    for index, spec in enumerate(step.get("asserts", [])):
        try:
            await run_assert(page, spec)
        except StepFailed as exc:
            raise StepFailed(
                exc.code, exc.message, where=f"asserts[{index}].target"
            ) from exc

    return result


def _as_failure(exc: BaseException, *, code: str | None = None) -> StepFailed:
    """把各种异常统一成 StepFailed，便于上层记录。"""
    if isinstance(exc, StepFailed):
        if code is None:
            return exc
        return StepFailed(code, exc.message, where=exc.where)
    return StepFailed(code or "STEP_TIMEOUT", "等不到预期状态")


async def _try_repair(
    hook: RepairHook | None,
    page: Page,
    step: dict[str, Any],
    failure: StepFailed,
) -> RepairDecision | None:
    """判定能不能修，然后调用修复钩子。

    修复器自己抛异常一律当"修不了"——自愈是加分项，不能把主流程带崩。
    """
    if hook is None or failure.code not in LOCATE_ERRORS:
        return None
    try:
        return await hook(page, step, failure)
    except Exception as exc:  # noqa: BLE001
        print(f"  [自愈] 修复器异常，放弃：{exc!r}")
        return None


def _fail(
    done: list[StepResult],
    outputs: dict[str, Any],
    fixes: list[RepairRecord],
    step: dict[str, Any],
    failure: StepFailed,
    started: float,
    decision: RepairDecision | None = None,
) -> RunResult:
    print(f"  [{step['seq']}] {step['intent']} … 失败 [{failure.code}] {failure.message}")
    done.append(_step_result(step, "failed", failure, started))

    # 试过修但重试没过：要留痕，"修过没修好"和"根本没修"是两回事
    failed_repair: RepairRecord | None = None
    if decision is not None:
        failed_repair = RepairRecord(
            seq=step["seq"],
            where=failure.where,
            old_target=step.get("target"),
            new_target=decision["step"].get("target"),
            confidence=decision["confidence"],
            rationale=decision["rationale"],
            model=decision["model"],
        )

    return RunResult(
        ok=False,
        outputs=outputs,
        steps=done,
        fixes=fixes,
        failed_repair=failed_repair,
        failed_step=step["seq"],
        failed_where=failure.where,
        reason_code=failure.code,
        reason_message=failure.message,
    )


async def replay(
    recipe: dict[str, Any],
    steps: list[dict[str, Any]],
    *,
    repair: RepairHook | None = None,
    page: Page | None = None,
) -> RunResult:
    """跑一份配方。

    page 不为空时在给定页面上跑——会话层登录后把页面交过来，
    业务配方就不必再自己开浏览器、也不必重复登录。
    """
    if page is not None:
        return await replay_on(page, recipe, steps, repair)

    async with async_playwright() as p:
        # 服务器没有桌面，必须无头；本地想看它跑就设 BROWSER_HEADLESS=0
        browser = await p.chromium.launch(headless=config.BROWSER_HEADLESS)
        own_page = await browser.new_page()
        try:
            return await replay_on(own_page, recipe, steps, repair)
        finally:
            await browser.close()


async def replay_on(
    page: Page,
    recipe: dict[str, Any],
    steps: list[dict[str, Any]],
    repair: RepairHook | None = None,
) -> RunResult:
    """在已有页面上按序执行步骤。不负责开/关浏览器。"""
    base_url = recipe["base_url"].rstrip("/")
    outputs: dict[str, Any] = {}
    done: list[StepResult] = []
    fixes: list[RepairRecord] = []

    print(f"配方 {recipe['name']} v{recipe['version']}，共 {len(steps)} 步")

    for index, step in enumerate(steps):
        label = f"  [{step['seq']}] {step['intent']}"
        started = time.perf_counter()
        try:
            result = await _run_step(page, step, base_url)
        except (StepFailed, PlaywrightTimeoutError) as exc:
            failure = _as_failure(exc)
            decision = await _try_repair(repair, page, step, failure)
            if decision is None:
                return _fail(done, outputs, fixes, step, failure, started)

            fixed = decision["step"]
            print(f"{label} … 定位失败，自愈后重试")
            try:
                result = await _run_step(page, fixed, base_url)
            except (StepFailed, PlaywrightTimeoutError) as retry_exc:
                # 修完还失败：到此为止，不降级、不跳过
                return _fail(
                    done,
                    outputs,
                    fixes,
                    step,
                    _as_failure(retry_exc, code="LOCATE_DRIFT_UNREPAIRED"),
                    started,
                    decision,
                )

            steps[index] = fixed
            fixes.append(
                RepairRecord(
                    seq=step["seq"],
                    where=failure.where,
                    old_target=step.get("target"),
                    new_target=fixed.get("target"),
                    confidence=decision["confidence"],
                    rationale=decision["rationale"],
                    model=decision["model"],
                )
            )

        done.append(_step_result(step, "ok", None, started))

        if "as" in step and result is not None:
            outputs[step["as"]] = result
        print(f"{label} … ok")

    return RunResult(
        ok=True,
        outputs=outputs,
        steps=done,
        fixes=fixes,
        failed_repair=None,
        failed_step=None,
        failed_where=None,
        reason_code=None,
        reason_message=None,
    )