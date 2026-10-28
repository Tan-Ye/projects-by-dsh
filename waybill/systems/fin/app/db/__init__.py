"""数据层入口。

调用方只认这个模块：
    from ..db import get_db, get_user, VoucherInput
内部按表域拆分，怎么分不需要外面知道。
"""

from __future__ import annotations

from .connection import SCHEMA_FILE, connect, get_db, init_db
from .meta import (
    get_account,
    get_accounts,
    get_cost_center,
    get_cost_centers,
    get_department,
    get_departments,
)
from .models import (
    AccountRow,
    CostCenterRow,
    DepartmentRow,
    SessionRow,
    UserRow,
    VoucherDetail,
    VoucherErrorRow,
    VoucherInput,
    VoucherLineInput,
    VoucherLineRow,
    VoucherPage,
    VoucherRow,
)
from .passwords import PBKDF2_ITERATIONS, hash_password, verify_password
from .seed import seed
from .timefmt import now_str
from .users import create_session, get_session, get_user
from .vouchers import (
    create_voucher,
    get_voucher,
    list_vouchers,
    mark_approved,
    mark_pending,
    mark_rejected,
    next_voucher_no,
    replace_voucher,
)

__all__ = [
    # 连接
    "connect",
    "get_db",
    "init_db",
    "SCHEMA_FILE",
    # 密码
    "hash_password",
    "verify_password",
    "PBKDF2_ITERATIONS",
    # 种子
    "seed",
    # 时间
    "now_str",
    # 用户与会话
    "get_user",
    "create_session",
    "get_session",
    # 元数据
    "get_accounts",
    "get_account",
    "get_departments",
    "get_department",
    "get_cost_centers",
    "get_cost_center",
    # 凭证
    "create_voucher",
    "replace_voucher",
    "get_voucher",
    "list_vouchers",
    "next_voucher_no",
    "mark_pending",
    "mark_approved",
    "mark_rejected",
    # 类型
    "UserRow",
    "AccountRow",
    "DepartmentRow",
    "CostCenterRow",
    "SessionRow",
    "VoucherRow",
    "VoucherLineRow",
    "VoucherErrorRow",
    "VoucherLineInput",
    "VoucherInput",
    "VoucherDetail",
    "VoucherPage",
]
