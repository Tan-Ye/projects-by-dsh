"""密码哈希。

存进库里的格式：`pbkdf2_sha256$迭代次数$salt$hash`。
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

PBKDF2_ITERATIONS = 120_000


def hash_password(raw: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    """生成 pbkdf2_sha256$迭代次数$salt$hash。

    盐每次随机，所以同一个密码两次调用的结果不同——这是对的。
    迭代次数和盐都必须存进串里，否则验证时算不回来。
    """
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", raw.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(raw: str, stored: str) -> bool:
    """用 stored 里自己的盐和迭代次数重算，再定长比较。

    不能重新调 hash_password —— 它会生成新盐，结果永远对不上。
    """
    try:
        algo, iterations, salt_hex, hash_hex = stored.split("$")
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False

    digest = hashlib.pbkdf2_hmac(
        "sha256", raw.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
    )
    # 定长比较：用 == 会在第一个不同字节处返回，泄漏前缀匹配长度
    return hmac.compare_digest(digest.hex(), hash_hex)
