# 组件与目录规范 · 完整版

**适用范围**：目录划分、模块边界、导出方式、组件拆分。样式相关见 [../style/full.md](../style/full.md)，项目特有约定见 [project/frontend.md](../../../project/frontend.md)。

**目标**：任何一个文件都能在 10 秒内找到它该在哪；改一个模块时，能明确知道影响范围不会扩散。

---

## 1. 目录结构

```
src/
├── pages/              路由级页面
├── components/         跨页面复用的展示组件
├── services/           接口层
├── hooks/              跨页面复用的状态逻辑
├── utils/              纯函数
├── types/              被多处使用的类型
└── styles/             全局样式
```

**判据不是"文件属于什么类型"，而是"谁能用"**：

- 只有某个页面用的组件 → 留在页面文件里，不进 `components/`
- 只有某个组件用的函数 → 留在那个组件文件里，不进 `utils/`

过早抽到公共目录，代价是每次改动都要判断"有没有别人在用"。

---

## 2. 命名

**所有文件名一律 kebab-case，全小写。**

```
order-list.tsx         ✅
OrderList.tsx          ❌
orderList.tsx          ❌
```

组件文件也是小写，里面的导出名仍然用 PascalCase：

```tsx
// pages/order-list.tsx
export function OrderList() { ... }
```

**为什么不用 PascalCase**：Windows 文件名不区分大小写，Linux 区分。`OrderList.tsx` 和 `orderList.tsx` 在开发机上是同一个文件，推到 Linux 构建才报错。全小写让这类问题从根上不存在。

---

## 3. 导出

除框架强制要求（如 `vite.config.ts`、`main.tsx` 的入口挂载）外，**一律具名导出**。

```ts
export function listOrders() {}      // ✅
export default function () {}          // ❌ 引用方可以随便改名
```

具名导出的好处：重命名时 IDE 能全局追踪；`default` 导出则允许 `import whatever from './x'`，同一个模块在不同文件里有不同名字，搜索就失效了。

**同一模块内，组件/函数/hook 不允许重名。** 跨模块同名不可避免，但要能一眼区分用途（`formatDate` / `formatMoney`，而不是两个 `format`）。

---

## 4. utils：只放纯函数

```ts
// utils/money.ts
export function centsToYuan(cents: number): string {
  return (cents / 100).toFixed(2)
}
```

判据：**同样的输入永远得到同样的输出，不依赖时间、网络、localStorage、React。**

一旦 `utils` 里出现了 `fetch`，它就不再是工具库，而是第二层 services——边界模糊、单测要 mock 网络、复用时会带上副作用。

按用途分文件：`format.ts`、`money.ts`、`validate.ts`。不要一个 `helpers.ts` 什么都装。

**统一函数不为特例加开关**：`formatDate` 就是全项目统一格式。某一处需要不同格式，就在那一处单独处理，不要给 `formatDate` 加 `'short' | 'long' | 'cn'` 参数——那会变成第二个、第三个，直到函数没人敢改。

三次法则：同一个变体出现到第三处，新增一个具名函数（`formatDateShort`），而不是继续手写。

---

## 5. hooks：状态逻辑

```ts
// hooks/use-order-detail.ts
export function useOrderDetail(id: number) {
  const [detail, setDetail] = useState<OrderDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async () => { ... }, [id])
  useEffect(() => { void reload() }, [reload])

  return { detail, loading, error, reload }
}
```

- 文件名以 `use` 开头
- **返回对象，不返回数组**——以后加字段不用改所有调用方
- 只放跨页面复用的；只服务一个页面的 hook 留在页面文件里

---

## 6. services：一个函数一个接口

```
services/
└── order/
    ├── index.ts        函数调用与传参
    └── interface.ts    请求/响应/领域类型
```

**`index.ts` 只写"怎么调"**：

```ts
export function listOrders(query: OrderQuery): Promise<OrderPage> {
  return http.get('/orders', { params: query })
}
```

**`interface.ts` 只写类型**，不写任何运行时代码。

**一个函数只对应一个后端接口，service 之间不许互相调用。**

```ts
// ❌ 建单后顺手查一下科目——这是编排，不是接口
export async function createOrder(data) {
  const accounts = await listAccounts()      // 另一个 service
  ...
}
```

出现这种代码说明业务是"多接口协调"的，它应该上移到 hook 或页面：

```ts
// hooks/use-create-order.ts
async function submit(data) {
  const accounts = await listAccounts()
  const enriched = enrich(data, accounts)
  return createOrder(enriched)
}
```

**为什么不放 utils**：编排要发请求、有顺序、可能失败，它不满足纯函数定义。放进去会让 `utils` 变成第二层 services。

**services 不碰 UI**：不发 `message.error`、不做路由跳转、不读写 localStorage。它只负责"发请求、把 HTTP 错误翻成 ApiError、返回类型"。怎么提示是页面的事。

---

## 7. 组件：展示与数据分离

- **展示组件**（`components/`）只接收 props、抛事件，不直接调 `services`
- **数据获取**放在页面或 hook 里

这样组件可以被单独渲染、单独预览，接口变了也不会连带改动。

**props 用 `interface` 声明**：

```tsx
interface OrderLineRowProps {
  line: OrderLine
  onChange: (line: OrderLine) => void
}
```

- 对象形状 → `interface`，命名为 `XxxProps`
- 联合类型、基础类型别名 → `type`

```ts
type OrderStatus = 'draft' | 'submitted' | 'voided'    // 联合用 type
```

复用别的组件的 props 时用 `interface extends`：

```ts
interface FinButtonProps extends ButtonProps {
  loadingText?: string
}
```

**单个组件 200–300 行以内。** 行数只是信号，真正的判据是"这里面是不是有两组不相关的状态"——两组状态互不影响，就该拆成两个组件。

---

## 8. 依赖方向

```
pages  →  components / services / hooks / utils / types
components  →  services? 否；hooks / utils / types ✅
services  →  utils / types
```

三条禁止：

- `components` 不 import `pages`
- `services` 不 import 任何 UI（组件、hooks、样式）
- `utils` 不 import 以上任何一层（除了 types）

**依赖成环的代价**：改 A 不知道会不会影响 B，构建时循环依赖会让模块初始化顺序变得不可预测，热更新也会失灵。

---

## 9. 路径与 barrel

**跨三层以上目录一律用 `@/` 别名**：

```ts
import { listOrders } from '@/services/order'    // ✅
import { listOrders } from '../../../services/order'   // ❌
```

**`utils/` 和 `hooks/` 各有一个 `index.ts` 做导出入口**：

```ts
// utils/index.ts
export * from './format'
export * from './money'
```

两条约束：

1. **模块内部文件不许从自己的 `index.ts` 引入**（`format.ts` 引 `index.ts`，而 index 又导出 format → 循环依赖）
2. **`index.ts` 只做导出，不写逻辑**

**不建全局大 barrel**：不要 `services/index.ts` 把全部服务再导出一遍。那会让循环依赖变得非常容易踩，也会让打包时把一个模块的依赖拖进另一个模块。

---

## 10. 类型放哪

```
src/types/          被 2 个以上模块使用的类型
services/x/interface.ts   只被这个接口模块使用的类型
```

判据就一条：**被 2 处以上用才进 `types/`**。否则 `types/` 会变成垃圾场，每个新概念都往里扔，最后没人知道某个类型为什么会存在。

`types/` 过多时按功能分文件（`common.ts`、`order.ts`、`user.ts`），并有一个 `index.ts` 做入口。
