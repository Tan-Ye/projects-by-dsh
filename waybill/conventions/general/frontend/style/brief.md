# 前端样式规则 · 精简版

每条规则配一个能直接抄的示例。只有规则看 [rules.md](rules.md)，要理由看 [full.md](full.md)。

| # | 规则 | 示例 |
|---|---|---|
| 1 | 预处理器二选一 | 项目内只用 `scss` |
| 2 | 有组件库不引 tailwind | AntD 项目不装 tailwind |
| 3 | 页面样式用 CSS Module | `OrderEdit.module.scss` |
| 4 | Module 类名 camelCase | `.lineRow` |
| 5 | 页面 module 只写布局 | 不写 `.ant-btn` 覆盖 |
| 6 | 公共组件禁用 Module | `.ui-btn__icon`（全局） |
| 7 | 根元素带组件类名 | `<Button className="ui-btn">` |
| 8 | 穿透用 `:global` | `:global(.ui-btn) { ... }` |
| 9 | 穿透只改表现 | 颜色/字号/间距，不改 `display` |
| 10 | 重封装不改内部 class | 包一层，不写 `.ant-btn-primary` |
| 11 | 三种手段按优先级 | theme → 重封装 → 穿透 |
| 12 | 全局样式只有一个文件 | `src/styles/global.scss` |
| 13 | 颜色走 token | `var(--ui-primary)` |
| 14 | 嵌套 ≤ 3 层 | `!important` 必须注释 |
| 15 | 状态类名 `is-` 前缀 | `is-loading` |
| 16 | 禁止行内 style | 动态值除外 |
| 17 | 组件头声明可覆盖类名 | JSDoc 列出 `ui-btn__*` |
| 18 | 断点集中定义 | `@include lg { }` |
| 19 | 间距 4 的倍数 | `8 / 12 / 16`，1px 边框优先 flex 居中 |
| 20 | 不写魔法数字 | 间距走变量 |
| 21 | module 超 150 行拆组件 | — |

## 完整示例

```scss
// components/FinButton/index.scss —— 公共组件，全局类名
.ui-btn {
  padding: 0 16px;          // 4 的倍数
  border-radius: var(--ui-radius);   // token，不写死 4px

  &__icon { margin-right: 8px; }
  &.is-loading { opacity: 0.6; }
}
```

```scss
// pages/OrderEdit.module.scss —— 页面，CSS Module
.toolbar {
  display: flex;
  gap: 8px;
}

:global(.ui-btn) {
  :global(.ui-btn__icon) { color: #fff; }   // 只改表现
}
```
