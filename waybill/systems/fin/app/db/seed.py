"""种子数据。

每张表先看行数，已经有数据就跳过——保证 init_db() 能反复跑。
"""

from __future__ import annotations

from .passwords import hash_password
import sqlite3

AccountSeed = tuple[str, str, str | None, int, int, int, int]
DepartmentSeed = tuple[str, str]
CostCenterSeed = tuple[str, str, str, int]
UserSeed = tuple[str, str, str, str]

# 顺序不能反：父科目必须先于子科目插入，否则自引用外键过不去
ACCOUNTS: list[AccountSeed] = [
    # code,       name,      parent,     level, is_leaf, is_active, sort
    ("6601", "管理费用", None, 1, 0, 1, 1),
    ("6601.01", "差旅费", "6601", 2, 1, 1, 1),
    ("6601.03", "交通费", "6601", 2, 1, 1, 2),
    ("6601.04", "业务招待费", "6601", 2, 1, 1, 3),
    ("6601.05", "办公费", "6601", 2, 0, 1, 4),
    ("6601.05.01", "办公用品", "6601.05", 3, 1, 1, 1),
    ("6601.05.02", "快递费", "6601.05", 3, 1, 1, 2),
    ("6601.09", "会议费", "6601", 2, 1, 0, 5),
]

DEPARTMENTS: list[DepartmentSeed] = [
    ("RD", "研发部"),
    ("MKT", "市场部"),
    ("SALES", "销售部"),
    ("ADM", "行政部"),
    ("FIN", "财务部"),
    ("HR", "人力资源部"),
]

COST_CENTERS: list[CostCenterSeed] = [
    # code,           name,        dept,    is_default
    ("CC-RD-01", "研发中心", "RD", 1),
    ("CC-RD-02", "测试中心", "RD", 0),
    ("CC-MKT-01", "市场部", "MKT", 1),
    ("CC-MKT-02", "品牌组", "MKT", 0),
    ("CC-SALES-01", "销售一部", "SALES", 0),
    ("CC-SALES-02", "销售二部", "SALES", 1),
    ("CC-ADM-01", "行政部", "ADM", 1),
    ("CC-ADM-02", "后勤组", "ADM", 0),
    ("CC-FIN-01", "财务部", "FIN", 1),
    ("CC-FIN-02", "资金组", "FIN", 0),
    ("CC-FIN-03", "税务组", "FIN", 0),
    ("CC-HR-01", "人力资源部", "HR", 1),
    ("CC-HR-02", "培训组", "HR", 0),
]

USERS: list[UserSeed] = [
    # username,  password,     display_name, role
    ("maker", "maker123", "张制单", "maker"),
    ("checker", "checker123", "李复核", "checker"),
]


def seed(conn: sqlite3.Connection) -> None:
    """灌科目树 / 部门 / 成本中心 / 账号。

    插入顺序按外键依赖排：科目先父后子，部门先于成本中心。
    """
    if conn.execute("SELECT COUNT(*) AS n FROM accounts").fetchone()["n"] == 0:
        conn.executemany(
            "INSERT INTO accounts (code, name, parent_code, level, is_leaf, is_active, sort)"
            " VALUES (?,?,?,?,?,?,?)",
            ACCOUNTS,
        )

    if conn.execute("SELECT COUNT(*) AS n FROM departments").fetchone()["n"] == 0:
        conn.executemany(
            "INSERT INTO departments (code, name) VALUES (?,?)",
            DEPARTMENTS,
        )

    if conn.execute("SELECT COUNT(*) AS n FROM cost_centers").fetchone()["n"] == 0:
        conn.executemany(
            "INSERT INTO cost_centers (code, name, dept_code, is_default) VALUES (?,?,?,?)",
            COST_CENTERS,
        )

    if conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 0:
        conn.executemany(
            "INSERT INTO users (username, password_hash, display_name, role) VALUES (?,?,?,?)",
            [(u, hash_password(p), d, r) for u, p, d, r in USERS],
        )
