"""跑一条任务：配方 → 浏览器 → 证据 → 财务 → 状态。

返回 (任务终态, 一句话结论)，终态 ∈ succeeded / waiting_human / failed。
退出码是 CLI 的事，流程层不掺和。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import config
import store
from browser.repair import make_repairer
from browser.replay import RepairHook, RunResult, load_recipe, render, replay
from errors import AgentError
from flows.voucher import write_to_finance
from llm import LlmClient
from playwright.async_api import Page
from reason_codes import needs_human


def write_back_recipe(recipe: dict[str, Any], steps: list[dict[str, Any]]) -> Path:
    """自愈成功后把新配方写回文件，版本 +1。

    配方是文件、git 是历史：这次改动在 diff 里看得见，能 review、能回滚。
    """
    spec = {**recipe, "version": int(recipe["version"]) + 1, "steps": steps}
    path = config.RECIPE_DIR / f"{recipe['name']}.json"
    path.write_text(
        json.dumps(spec, ensure_ascii=False, indent=4) + "\n", encoding="utf-8"
    )
    return path


def _record_repairs(
    conn: sqlite3.Connection,
    run_id: int,
    recipe_name: str,
    run: RunResult,
) -> None:
    """把自愈结果写库。成功的、失败的都记。"""
    for fix in run["fixes"]:
        store.add_repair(
            conn,
            run_id,
            recipe_name=recipe_name,
            step_seq=fix["seq"],
            target_path=fix["where"],
            old_target=fix["old_target"],
            new_target=fix["new_target"],
            confidence=fix["confidence"],
            rationale=fix["rationale"],
            outcome="retried_ok",
        )

    failed = run["failed_repair"]
    if failed is not None:
        store.add_repair(
            conn,
            run_id,
            recipe_name=recipe_name,
            step_seq=failed["seq"],
            target_path=failed["where"],
            old_target=failed["old_target"],
            new_target=failed["new_target"],
            confidence=failed["confidence"],
            rationale=failed["rationale"],
            outcome="retried_failed",
        )


def _build_repairer() -> tuple[RepairHook | None, LlmClient | None]:
    """建自愈钩子。没有 key 就退化成"不自愈"，不能让主流程崩。"""
    try:
        client = LlmClient.from_config()
    except RuntimeError as exc:
        print(f"  [自愈] 不可用：{exc}")
        return None, None
    return make_repairer(client), client


async def execute_task(
    conn: sqlite3.Connection,
    *,
    task_id: int | None,
    task_name: str,
    recipe_name: str,
    inputs: dict[str, str],
    page: Page | None = None,
    repair: RepairHook | None = None,
) -> tuple[str, str]:
    """跑一条任务，全程留痕。返回 (任务终态, 一句话结论)。

    page 不为空时在会话层已登录的页面上跑——登录只做一次，
    这一条任务从第一步业务动作开始。

    repair 为空时自己建一个修复器（单条调试用）；批次会传一个共用的，
    避免每单都新建一个模型客户端。

    配置错误（缺配方、缺参数）由 StepFailed 抛出，交给调用方决定
    标记成 failed 还是直接退出——worker 和 CLI 的处理不一样。
    """
    recipe = load_recipe(recipe_name)
    steps = render(recipe["steps"], inputs)

    # 先建 run 再跑：中途崩溃也留得下一条 running 记录
    run_id = store.create_run(
        conn,
        task_id=task_id,
        task_name=task_name,
        recipe_name=recipe["name"],
        recipe_version=int(recipe["version"]),
    )
    # 配方快照：事后要能回答"这次用的是哪份配方"，光有版本号不够
    store.add_extraction(conn, run_id, "recipe", recipe)

    own_client: LlmClient | None = None
    hook = repair
    if hook is None:
        hook, own_client = _build_repairer()

    try:
        run = await replay(recipe, steps, repair=hook, page=page)
    finally:
        if own_client is not None:
            await own_client.aclose()

    store.add_steps(conn, run_id, list(run["steps"]))
    _record_repairs(conn, run_id, recipe["name"], run)

    if not run["ok"]:
        code = run["reason_code"] or "STEP_FAILED"
        # 有些执行失败不是"我们出错了"，而是"数据不完整，得人来判断"
        # （比如明细分页只读到第一页）
        status = "waiting_human" if needs_human(code) else "failed"
        message = f"[{code}] 第 {run['failed_step']} 步失败：{run['reason_message']}"
        store.finish_run(
            conn,
            run_id,
            status=status,
            reason_code=code,
            reason_message=run["reason_message"],
        )
        return status, message

    # 自愈成功：配方升级一版，下次直接按新配方跑，不再问模型
    if run["fixes"] and not recipe.get("fixture"):
        path = write_back_recipe(recipe, steps)
        print(f"  [自愈] 配方已回写 {path.name}（v{int(recipe['version']) + 1}）")

    # 先落证据，再做任何变换：后面建单失败、核验不一致，证据都还在
    for name, payload in run["outputs"].items():
        store.add_extraction(conn, run_id, name, payload)

    doc_no = str((run["outputs"].get("doc") or {}).get("单号", "")).strip()
    if doc_no:
        store.set_external_ref(conn, run_id, doc_no)

    try:
        message = await write_to_finance(conn, run_id)
    except AgentError as exc:
        status = "waiting_human" if needs_human(exc.code) else "failed"
        print(f"  {exc}")
        store.finish_run(
            conn,
            run_id,
            status=status,
            reason_code=exc.code,
            reason_message=exc.message,
        )
        return status, str(exc)

    store.finish_run(conn, run_id, status="succeeded", reason_message=message)
    return "succeeded", message
