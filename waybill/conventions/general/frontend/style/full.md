# 前端样式规范 · 完整版

**适用范围**：所有前端样式代码。项目特有的约定见 [project/frontend.md](../../../project/frontend.md)。
只有规则看 [rules.md](rules.md)，规则加示例看 [brief.md](brief.md)。组件与目录规则见 [../structure/full.md](../structure/full.md)。

**目标**：公共组件的类名和页面的类名互不影响——改一个页面不会波及其他页面，公共组件有一个稳定、可查的样式入口。

---

## 1. 预处理器

less / scss 二选一，同一项目内不混用。两者能力接近，混用只会让构建多一条链路。

**有组件库的项目不引入 tailwind。** AntD、Element 这类库自带样式体系和主题变量，再叠一层原子类，同一个视觉会有两个来源，改起来先要判断"这条样式是谁生效的"。

没有组件库、纯自绘的项目，tailwind 很划算。

---

## 2. 页面组件：CSS Module

```scss
// pages/OrderEdit.module.scss
.toolbar { display: flex; gap: 8px; }
.lineRow { padding: 8px 0; }
```

- 文件名与组件同名：`OrderEdit.tsx` ↔ `OrderEdit.module.scss`
- 类名 camelCase：`.lineRow`，不写 `.line-row`——JS 里 `styles.lineRow` 才对得上
- 只写布局和页面独有的表现，不写公共组件的内部样式

CSS Module 的作用是**隔离**：这个页面里的 `.toolbar` 和别的页面的 `.toolbar` 互不影响。

---

## 3. 公共组件：全局类名 + 前缀 + BEM

公共组件**禁止使用 CSS Module**。理由很直接：Module 会把类名哈希成 `_btn_x7f2a`，外部无法稳定命中，第 8 条的穿透就不成立了。

```scss
// components/UiButton/index.scss
.ui-btn { padding: 0 16px; }
.ui-btn__icon { margin-right: 8px; }
.ui-btn--loading { opacity: 0.6; }
```

```tsx
// components/UiButton/index.tsx
/**
 * 财务项目通用按钮。
 *
 * 可覆盖的类名：
 *   ui-btn           根
 *   ui-btn__icon     图标
 *   ui-btn--loading  加载态
 */
export function UiButton(props: ButtonProps) {
  return <Button className="ui-btn" {...props} />
}
```

**根元素必须带组件级类名**，这是唯一的对外入口。前缀避免两个组件都叫 `.header` 撞车。

**文件头必须声明可覆盖的类名**——否则外部用的时候只能翻源码猜。

---

## 4. 外部怎么改公共组件的样式

在使用方页面的 module 里用 `:global` 穿透：

```scss
// pages/OrderEdit.module.scss
:global(.ui-btn) {
  :global(.ui-btn__icon) { color: #fff; }
}
```

两处都要 `:global`：外层不加，`.ui-btn` 会被哈希；内层不加，`.ui-btn__icon` 也会被哈希。

**只允许改表现属性**：颜色、字号、间距、圆角。不允许改布局结构（`display`、`position`、子元素顺序）——结构有意见就改组件本身，否则组件内部永远不能重构。

---

## 5. 改样式的优先级

只允许三种手段，按顺序取第一个能满足的：

| 顺序 | 手段 | 场景 |
|---|---|---|
| 1 | 主题配置（`ConfigProvider` 的 `theme.token` / `components`） | 全局视觉统一改 |
| 2 | 重封装组件 + 前缀类名 | 某个组件的标准样式不同 |
| 3 | 页面 module 里 `:global` 穿透 | 单页的一次性调整 |
| ✗ | 直接写第三方内部 class（`.ant-btn-primary`） | **禁止** |

直接写第三方内部 class 的问题：类名是库的私有实现，升级即失效，而且散落在各处无法统计。

---

## 6. 全局样式与变量

**全局样式只允许一个文件**：`src/styles/global.scss`，只放 reset 和 CSS 变量。

组件里禁止 `import` 全局 css——打包顺序不可控，同一个选择器在不同页面可能表现不同。

**design token 集中管理**：

```scss
:root {
  --ui-primary: #1677ff;
  --ui-radius: 4px;
  --ui-gap: 8px;
}
```

组件内禁止写死 `#1677ff`。颜色改一次要改二十个文件，就是从这里开始的。

---

## 7. 嵌套与优先级

- **嵌套不超过 3 层**，再深就说明结构该拆了
- **`!important` 只用于覆盖第三方库**，且必须写注释说明为什么非它不可

```scss
// 覆盖 AntD 的 message 层级，它的样式优先级比页面高，只能强制
:global(.ant-message) { z-index: 2000 !important; }
```

---

## 8. 命名

- 状态类统一 `is-` 前缀：`is-active` / `is-disabled` / `is-loading` / `is-error`
- 不用 `.active` / `.on` / `.cur` 这类各写各的
- 公共组件：`前缀-组件` + `__元素` + `--修饰符`

---

## 9. 数值

**间距默认取 4 的倍数**：4 / 8 / 12 / 16 / 24 / 32。

无法满足时取偶数。**因为 1px 边框导致只能取奇数时，优先改用 flex 居中来规避**——比如"高度 31px 的按钮"，正确做法是 `height: 32px` + `display: flex; align-items: center`，而不是把 padding 写成 7px 去凑。

样式里不写魔法数字，间距走变量或 4 的倍数。

---

## 10. 可维护性

- 禁止行内 `style`，动态计算值（按数据算的宽度百分比）除外——行内样式优先级最高，会把上面整套优先级打乱
- 断点集中定义，页面里不写裸数字：

```scss
// global.scss
@mixin lg { @media (min-width: 1200px) { @content; } }
```

- 单个 module 文件超过 150 行，说明这个页面该拆组件了
