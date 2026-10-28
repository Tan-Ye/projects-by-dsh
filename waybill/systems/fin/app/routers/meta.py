"""元数据：科目树、部门、成本中心。

这三份数据是前端联动的依据，也是 agent 判断"该填什么"的来源。
"""

from __future__ import annotations

from sqlite3 import Connection
from typing import cast

from fastapi import APIRouter, Depends

from ..db import (
    AccountRow,
    CostCenterRow,
    DepartmentRow,
    get_accounts,
    get_cost_centers,
    get_db,
    get_department,
    get_departments,
)
from ..deps import current_user
from ..errors import ApiError

# 鉴权挂在路由级：这三个接口只需要"必须先登录"，不需要知道是谁。
# 以后哪个接口要用到当前用户，再单独在参数里声明，FastAPI 按请求缓存依赖，不会执行两次。
router = APIRouter(tags=["meta"], dependencies=[Depends(current_user)])


class AccountNode(AccountRow):
    """科目树节点：一行科目数据 + 它的子节点。"""

    children: list["AccountNode"]


def _build_tree(rows: list[AccountRow]) -> list[AccountNode]:
    """把按层级排好序的扁平列表挂接成树。

    顺序由 SQL 的 ORDER BY 保证，这里只做父子挂接、不再排序——
    重排会破坏 sort 字段的语义。
    """
    nodes: dict[str, AccountNode] = {}
    for row in rows:
        # 行数据 + 空 children 就是节点，字段与 AccountNode 对齐
        nodes[row["code"]] = cast(AccountNode, {**row, "children": []})

    roots: list[AccountNode] = []
    for node in nodes.values():
        parent = node["parent_code"]
        if parent and parent in nodes:
            nodes[parent]["children"].append(node)
        else:
            roots.append(node)
    return roots


@router.get("/meta/accounts")
def accounts(conn: Connection = Depends(get_db)) -> list[AccountNode]:
    """科目树。

    每个节点都带 is_leaf 和 is_active：前端和 agent 靠 is_leaf 判断"选到哪一层算完"，
    靠 is_active 判断"能不能选"（停用科目要显示但要灰掉）。
    """
    return _build_tree(get_accounts(conn))


@router.get("/meta/departments")
def departments(conn: Connection = Depends(get_db)) -> list[DepartmentRow]:
    """启用中的部门，按编码排序。"""
    return get_departments(conn)


@router.get("/meta/cost-centers")
def cost_centers(dept: str, conn: Connection = Depends(get_db)) -> list[CostCenterRow]:
    """某部门可选的成本中心，默认的排最前。

    部门不存在或已停用直接 404。返回空列表会让"部门没了"和"部门没配成本中心"
    混成一件事，agent 就分不清该不该停下来找人确认。
    """
    department = get_department(conn, dept)
    if department is None or not department["is_active"]:
        raise ApiError(404, "NOT_FOUND", f"部门 {dept} 不存在或已停用")
    return get_cost_centers(conn, dept)
