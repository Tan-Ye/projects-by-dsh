# 代码规范

分两层：**general 可复用可开源，project 只属于本仓库。**

```
conventions/
├── manifest.json            # 语言 × 层级 × 级别 的映射，给安装脚本用
├── general/                 # ✅ 可以单独发到 GitHub
│   ├── python/{rules,brief,full}.md
│   ├── sql/{rules,brief,full}.md
│   └── frontend/
│       ├── style/{rules,brief,full}.md        # 样式
│       └── structure/{rules,brief,full}.md    # 组件、目录、模块边界
└── project/                 # ❌ 不外发，含业务信息
    ├── python.md
    ├── sql.md
    └── frontend.md
```

前端分两组：样式 21 条、组件与目录 20 条，合在一份太长，拆开各自成体系。

## 优先级

**project 覆盖 general。** 两者冲突时以 project 为准，因为项目规则是针对具体约束写的。

例：general 说"时间用 TEXT 定宽格式"，project 说"`sessions.expires_at` 用 unix 秒"——后者生效，且只在 `sessions` 这一张表上生效。

## general：三个级别

| 级别 | 文件 | 内容 | 给谁 |
|---|---|---|---|
| `rules` | `rules.md` | 只有规则，一屏看完 | 写代码时对照；**AI 只读这个** |
| `brief` | `brief.md` | 规则 + 一个能抄的示例 | Code review |
| `full` | `full.md` | 规则 + 完整示例 + 理由 + 反例 | 讨论"为什么这么定"、新人上手 |

`rules.md` 是唯一权威，另外两份以它为准。改一条规则，三个文件一起改。

## project：不分级

项目规则少、变动快，一眼能看完，不需要速查版。

## 为什么分两层

| 类型 | 例子 | 能开源吗 |
|---|---|---|
| 通用（语言级） | 禁止 `SELECT *`、`?` 占位传元组、`cast` 带理由 | ✅ 换任何项目都成立 |
| 项目特有（业务级） | 金额用分、`expires_at` 的例外、`external_ref` 的幂等含义 | ❌ 出去了别人用不上，还暴露表结构 |

**判断标准：一条规则换个项目就不成立，它就不该进 general。**

## 新增一门语言

给它建目录，不要往别人的文件里加"顺便也适用于 XX"的条目。同一个概念在不同语言里的最佳实践经常是冲突的：

- Python 数据层用 `TypedDict`（运行时就是 dict，零转换）
- TypeScript 里对应的是 `type` / `interface`，但还要管组件 props、state 形状

## 发布到独立仓库时的取法

`manifest.json` 里的 `publish.exclude` 已经把 `project/` 排除在外。安装脚本按 `languages` + 级别挑文件，拷进目标项目并在文件头写版本标记。

AI 侧只注入 `rules` 级别的内容——文件越少越短，遵守率越高。
