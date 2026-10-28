# Python 规则 · 精简版

每条规则配一个能直接抄的示例。只有规则看 [rules.md](rules.md)，要理由看 [full.md](full.md)。

| # | 规则 | 示例 |
|---|---|---|
| 1 | 数据库行用 `TypedDict` | `class UserRow(TypedDict): username: str` |
| 2 | 查询显式列名 | `SELECT id, name FROM users` |
| 3 | 领域对象用 `dataclass` | 构造校验 / 不变量 / 有行为 |
| 4 | 函数签名 100% 标注 | `def find_user(conn: Connection, name: str) -> UserRow \| None:` |
| 5 | 变量按需标注 | `retries: int = 3` |
| 6 | 编辑器类型检查常开 | Pylance `basic` |
| 7 | `docstring` 说"是什么" | `"""按用户名查用户；不存在返回 None。"""` |
| 8 | `#` 说"为什么" | `# 列名与 UserRow 对齐` |
| 9 | `cast` 必须带理由 | `cast(UserRow, dict(row))  # 列名与 UserRow 对齐` |
| 10 | 类型就近声明 | 响应类型写在 `fin_client.py`，不建全局 `models.py` |
| 11 | 拆分看行数和类型篇幅 | 类型占一半就拆 `fin_models.py`，不叫 `models.py` |

## 完整示例

```python
class UserRow(TypedDict):
    id: int
    username: str
    role: str


def find_user(conn: Connection, username: str) -> UserRow | None:
    """按用户名查用户；不存在返回 None。"""
    row = conn.execute(
        "SELECT id, username, role FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    # 列名与 UserRow 逐一对齐，见上面的 SELECT
    return cast(UserRow, dict(row)) if row is not None else None


@dataclass(frozen=True)
class Money:
    """金额：内部按分存，避免浮点误差。"""

    cents: int

    def __post_init__(self) -> None:
        if self.cents < 0:
            raise ValueError("金额不能为负")
```
