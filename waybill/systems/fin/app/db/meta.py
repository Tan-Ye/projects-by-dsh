"""元数据：科目、部门、成本中心。

注意两个命名相近的函数：
    get_departments  只取启用中的（给下拉框用）
    get_department   不过滤 is_active（给"区分不存在和已停用"的校验用）
成本中心同理。复用错了会让停用的数据在历史单据里变成空白。
"""

from __future__ import annotations

import sqlite3
from typing import cast

from .models import AccountRow, CostCenterRow, DepartmentRow


def get_accounts(conn: sqlite3.Connection) -> list[AccountRow]:
    """取整棵科目树，按层级 → 父节点 → 同级顺序排好。

    顺序很重要：前端和 agent 都按数组顺序组装层级、渲染下拉，
    顺序一乱，"选到哪一层算完"就判断错了。
    """
    rows = conn.execute(
        "SELECT code, name, parent_code, level, is_leaf, is_active, sort"
        " FROM accounts ORDER BY level, COALESCE(parent_code, ''), sort"
    ).fetchall()
    # 列名与 AccountRow 逐一对齐
    return [cast(AccountRow, dict(r)) for r in rows]


def get_departments(conn: sqlite3.Connection) -> list[DepartmentRow]:
    """取启用中的部门，按编码排序。"""
    rows = conn.execute(
        "SELECT code, name, is_active FROM departments WHERE is_active = 1 ORDER BY code"
    ).fetchall()
    # 列名与 DepartmentRow 逐一对齐
    return [cast(DepartmentRow, dict(r)) for r in rows]


def get_department(conn: sqlite3.Connection, code: str) -> DepartmentRow | None:
    """按编码查部门，**不过滤 is_active**——调用方要能区分"不存在"和"已停用"。"""
    row = conn.execute(
        "SELECT code, name, is_active FROM departments WHERE code = ?", (code,)
    ).fetchone()
    # 列名与 DepartmentRow 逐一对齐
    return cast(DepartmentRow, dict(row)) if row is not None else None


def get_cost_centers(conn: sqlite3.Connection, dept: str) -> list[CostCenterRow]:
    """取某部门启用中的成本中心，默认的排最前。

    排序在 SQL 里做：调用方直接拿第一项当默认值，顺序错了就会选错。
    """
    rows = conn.execute(
        "SELECT code, name, dept_code, is_default, is_active"
        " FROM cost_centers WHERE dept_code = ? AND is_active = 1"
        " ORDER BY is_default DESC, code",
        (dept,),
    ).fetchall()
    # 列名与 CostCenterRow 逐一对齐
    return [cast(CostCenterRow, dict(r)) for r in rows]


def get_account(conn: sqlite3.Connection, code: str) -> AccountRow | None:
    """按编码查科目，**不过滤 is_active / is_leaf**——校验需要区分具体情况。"""
    row = conn.execute(
        "SELECT code, name, parent_code, level, is_leaf, is_active, sort"
        " FROM accounts WHERE code = ?",
        (code,),
    ).fetchone()
    # 列名与 AccountRow 逐一对齐
    return cast(AccountRow, dict(row)) if row is not None else None


def get_cost_center(conn: sqlite3.Connection, code: str) -> CostCenterRow | None:
    """按编码查成本中心，**不过滤 is_active**——校验需要自己判断。"""
    row = conn.execute(
        "SELECT code, name, dept_code, is_default, is_active"
        " FROM cost_centers WHERE code = ?",
        (code,),
    ).fetchone()
    # 列名与 CostCenterRow 逐一对齐
    return cast(CostCenterRow, dict(row)) if row is not None else None
