"""页面文本 → 结构化数据。

这几个函数不依赖浏览器，也不依赖 Playwright。
好处是可以脱离页面单测：给它字符串，断言返回的数字。
"""

from __future__ import annotations

import re

# OA 的金额风格：￥1,286.00元 —— 货币符号、千分位、中文后缀
_MONEY = re.compile(r"^[\s￥¥]*(?P<yuan>[\d,]+)(?:\.(?P<cents>\d{1,2}))?[\s元]*$")


def parse_yuan(text: str) -> int:
    """'￥1,286.00元' → 128600（分）。解析失败抛 ValueError。

    为什么不 float():
        float("1286.00") * 100 可能得到 128599.99999999999
        金额必须走整数运算。
    """
    match = _MONEY.match(text)
    if match is None:
        raise ValueError(f"无法解析金额: {text!r}")

    yuan = int(match.group("yuan").replace(",", ""))
    # "1.5" 表示 1 元 5 角，要补成 50 分
    cents = int((match.group("cents") or "0").ljust(2, "0"))
    return yuan * 100 + cents


def rows_to_dicts(headers: list[str], rows: list[list[str]]) -> list[dict[str, str]]:
    """表头驱动：按列名取值，不依赖列的顺序。

    这就是抗漂移的关键——v2 档位换了列顺序，
    只要表头文字没变，这里读到的数据就还是对的。
    """
    return [dict(zip(headers, row)) for row in rows]

def normalize_label(text: str) -> str:
    r"""去掉所有空白，把"单 号"还原成"单号"。

    OA 的老页面用 &nbsp; 对齐，渲染出来是 \xa0，正则 \s 会一起吃掉。
    """
    return re.sub(r"\s+", "", text)


def parse_count(text: str) -> int:
    """"3 张" → 3。取不到数字就返回 0。"""
    match = re.search(r"\d+", text)
    return int(match.group()) if match else 0