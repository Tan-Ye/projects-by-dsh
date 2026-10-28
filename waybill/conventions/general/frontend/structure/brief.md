# 组件与目录规则 · 精简版

每条规则配一个能直接抄的示例。只有规则看 [rules.md](rules.md)，要理由看 [full.md](full.md)。

| # | 规则 | 示例 |
|---|---|---|
| 1 | 文件 kebab-case | `order-list.tsx` |
| 2 | 用具名导出 | `export function OrderList()` |
| 3 | 模块内不重名 | `formatDate` / `formatMoney` |
| 4 | utils 按用途分文件 | `utils/format.ts`、`utils/money.ts` |
| 5 | utils 只放纯函数 | 不 fetch、不读 localStorage |
| 6 | hook 放 hooks，`use` 开头 | `hooks/use-order.ts` |
| 7 | hook 返回对象 | `{ data, loading, error }` |
| 8 | services 分目录 | `services/order/{index,interface}.ts` |
| 9 | 两个文件各司其职 | `interface.ts` 只放类型 |
| 10 | 一个函数一个接口 | `listOrders()` 只调一个 URL |
| 11 | 多接口协调上移 | 放 hook 或页面 |
| 12 | services 不碰 UI | 不 `message.error`、不跳路由 |
| 13 | 展示组件不调 services | props 进，事件出 |
| 14 | 依赖单向 | `components` 不引 `pages` |
| 15 | utils/hooks 有 `index.ts` | `from '@/utils'` |
| 16 | index 只导出 | `export * from './format'` |
| 17 | types 只放共享类型 | 被 2 处以上用 |
| 18 | 深路径用别名 | `@/services/order` |
| 19 | props 用 interface | `interface OrderListProps {}` |
| 20 | 组件 200–300 行 | 超了拆子组件 |

## 目录总览

```
src/
├── pages/              路由级页面，一个路由一个文件
├── components/         跨页面复用的展示组件
│   └── ui-button/
│       ├── index.tsx
│       └── index.scss
├── services/           接口层，一个功能一个目录
│   └── order/
│       ├── index.ts        函数调用与传参
│       └── interface.ts    请求/响应/领域类型
├── hooks/              跨页面复用的状态逻辑
│   ├── index.ts
│   └── use-order-detail.ts
├── utils/              纯函数
│   ├── index.ts
│   ├── format.ts
│   └── money.ts
├── types/              被多处使用的类型
│   ├── index.ts
│   └── common.ts
└── styles/
    └── global.scss     唯一的全局样式
```

## 服务层写法

```ts
// services/order/interface.ts
export interface OrderQuery {
  status?: string
  page?: number
}
export interface OrderPage {
  total: number
  items: OrderRow[]
}
```

```ts
// services/order/index.ts
import { http } from '@/services/http'
import type { OrderPage, OrderQuery } from './interface'

export function listOrders(query: OrderQuery): Promise<OrderPage> {
  return http.get('/orders', { params: query })
}
```

## 编排放 hook

```ts
// hooks/use-order-detail.ts
export function useOrderDetail(id: number) {
  const [detail, setDetail] = useState<OrderDetail | null>(null)
  const [loading, setLoading] = useState(false)

  async function reload() {
    setLoading(true)
    try {
      setDetail(await getOrder(id))       // 只调一个 service
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void reload() }, [id])
  return { detail, loading, reload }        // 返回对象
}
```
