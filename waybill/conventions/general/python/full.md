# Python 规范 · 完整版

**适用范围**：所有 Python 代码。项目特有的补充见 [project/python.md](../../project/python.md)。
只有规则看 [rules.md](rules.md)，规则加示例看 [brief.md](brief.md)。

---

## 1. 数据库行用 `TypedDict`，禁止 `SELECT *`

```python
class UserRow(TypedDict):
    id: int
    username: str
    role: str
```

```python
# ✗ 加了一列，TypedDict 不知道
conn.execute("SELECT * FROM users WHERE username = ?", (username,))

# ✓ 列名写死
conn.execute(
    "SELECT id, username, role FROM users WHERE username = ?",
    (username,),
)
```

TypedDict 只在**列名固定**的前提下才成立。列一多一少，类型声明就和实际数据对不上，而且运行期不会有任何提示。

布尔列标 `int` 不标 `bool`——数据库驱动给出来的就是 0/1。

---

## 2. 领域对象用 `dataclass`，不是所有东西都该用

命中任一条件才用 `dataclass`：

| 条件 | 例子 |
|---|---|
| 需要**构造时校验** | 数据来自 JSON body、表单、外部接口 |
| 有**业务不变量** | 借贷必须平、序号必须连续、金额不能为负 |
| 有**行为** | 能不能提交、金额怎么汇总 |

```python
@dataclass(frozen=True)
class Money:
    """金额：内部按分存，避免浮点误差。"""

    cents: int

    def __post_init__(self) -> None:
        if self.cents < 0:
            raise ValueError("金额不能为负")
```

```python
@dataclass
class Order:
    external_no: str
    items: list[OrderItem] = field(default_factory=list)   # 不能用 = []
```

不命中的典型：纯查询结果、查出来马上序列化走。那类用 `TypedDict`。

反面判据："这个类以后可能会牵动很多文件" —— 写代码那一刻判断不了，不作为依据。

---

## 3. 类型标注

```python
def find_user(conn: Connection, username: str) -> UserRow | None:
```

函数签名 100% 标注。变量只在需要"定死类型"的地方标：

```python
retries = 3
retries = "three"      # ✗ 检查器不报：没声明类型，推断会变成 int | str

retries: int = 3
retries = "three"      # ✓ 这里标红：违反自己声明的契约
```

不用标的：`for i in range(...)`、循环里马上用掉的临时值。

**执行机制**：编辑器类型检查必须开着，否则注解只是注释。

- VS Code：`python.analysis.typeCheckingMode` = `basic`（Pylance）
- PyCharm：Settings → Editor → Inspections → Python → Type checker

命令行检查（`mypy`）可选，编辑器检查是底线。

---

## 4. `docstring` 说"是什么"，`#` 说"为什么"

```python
def find_user(conn: Connection, username: str) -> UserRow | None:
    """按用户名查用户；不存在返回 None。

    过滤停用账号放在这里，调用方不用每次都记得加。
    """
```

```python
# SQLite 默认不校验外键，每条连接都要单独打开
conn.execute("PRAGMA foreign_keys = ON")
```

- `docstring`：是什么、参数、返回、为什么这么设计
- `#`：为什么这么写（非显然的坑）

`docstring` 能被 IDE 悬浮显示、`help()` 读到，行注释不能——所以"是什么"必须写在 docstring 里。

自检：**需要一段注释才说得清"这块是干嘛的"，通常是函数名没起好。**

---

## 5. `cast` 必须带理由

```python
row = conn.execute(
    "SELECT id, username, role FROM users WHERE username = ?",
    (username,),
).fetchone()
# 列名与 UserRow 逐一对齐，见上面的 SELECT
return cast(UserRow, dict(row)) if row is not None else None
```

`cast` 是"我保证"，检查器会无条件相信。没有理由注释的 `cast`，等同于把类型系统关掉。

---

## 6. 类型就近声明

**判据**：这个类型描述的是**谁的东西**？谁拥有它，它就住在谁那里。

```python
# fin_client.py —— 描述财务 API 的响应，来源就是这里
class Department(TypedDict):
    code: str
    name: str
    is_active: int


class FinClient:
    async def departments(self) -> list[Department]:
        ...
```

`mapping.py` 需要用到它时，从这个文件导入：

```python
# mapping.py
from fin_client import Department
```

**单向依赖**：`mapping → fin_client`，反过来不行。

### 什么时候才该提升

必须**同时满足**两个条件：

1. 被 2 个以上模块使用
2. 不属于任何单一来源（谁都不是它的主人）

例：审计层的 `Provenance` 结构，client 和 mapping 都在用，但它描述的是"业务事实的来源"，不归任何一方——这才值得建公共模块。

只满足第 1 条的，仍然住在来源文件里，让别人 import。

### 文件太长怎么办

**两个判据，满足任一就拆**：

1. **实现行数**：翻文件找函数要找半天
2. **类型声明篇幅**：类型占了半个文件，实现反而被挤到下面

第二个判据容易被忽略。一个文件顶部堆十几个 `TypedDict`，虽然行数不多，但"改实现"时每次都要滚过一大段类型——这就是该拆的信号。

按来源拆，**名字里带来源**：

```
agent/
├── fin_models.py    ← 财务 API 的类型
├── fin_client.py    ← 实现，只放实现
└── mapping.py
```

拆完之后，消费方直接从类型文件导入，不从实现文件绕：

```python
from fin_client import FinClient
from fin_models import VoucherInput
```

不要建 `models.py`、`types.py`、`common.py`——这类名字没有主人，三个月后没人说得清某个类为什么在里面。

### 反例

```python
# models.py —— 什么都往里扔，最后变成垃圾场
class Department(TypedDict): ...
class Voucher(TypedDict): ...
class TaskStatus(TypedDict): ...
class Recipe(TypedDict): ...
```

三个系统、四个领域的概念挤在一个文件里。想看"财务 API 有哪些字段"，得先知道去 `models.py` 翻。

---

## 常见错误

| 写法 | 问题 | 正确 |
|---|---|---|
| `def f(conn, x)` | 参数无类型 | `def f(conn: Connection, x: str)` |
| `x = 10` 后 `x = "a"` | 没有契约，检查器只会改推断 | `x: int = 10` |
| `def f() -> list[dict]` 里塞 dataclass | 返回类型和实际不符 | 返回 `list[Row]` 或 `list[Model]` |
| `@dataclass` 里 `items = []` | 所有实例共用同一个列表 | `field(default_factory=list)` |
| `-> list[dict[str, Any]]` | 已经知道形状却丢掉 | `-> list[Department]` |
| 建全局 `models.py` | 无主类型聚集地 | 就近声明，或按来源拆文件 |
