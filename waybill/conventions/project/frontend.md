# 前端 · 项目特有约定

只适用于本仓库，覆盖 [general/frontend/style](../general/frontend/style/full.md) 与 [general/frontend/structure](../general/frontend/structure/full.md) 里的同名规则。
冲突时以本文件为准。

---

1. **预处理器用 scss**。三个前端项目统一，不混 less。构建侧只需 `sass` 一个依赖。

2. **本项目不引入 tailwind，也不引入 shadcn-ui**。三个应用都有明确形态：OA 与财务是中后台（AntD），控制台是产品界面但也用 AntD 保持一致性，不为它单独背一套样式体系。

3. **类名前缀按应用划分**：

   | 应用 | 前缀 | 例 |
   |---|---|---|
   | `systems/oa` | `oa-` | `oa-btn` |
   | `systems/fin/web` | `fin-` | `fin-btn` |
   | Waybill 控制台 | `wb-` | `wb-btn` |

4. **中后台页面一律用 AntD 标准组件**。需要统一视觉时先重封装，根元素加对应前缀类名，不改 AntD 内部 class。

5. **组件库只装一个**。一个前端应用里不同时出现 AntD 和别的 UI 库——两套 token、两套字体、两套间距，最终谁也说不出页面为什么长这样。

6. **共享组件目录**：`src/components/<组件名>/index.tsx` + `index.scss`，样式全局、类名带前缀。页面私有组件不进这个目录。

7. **全局样式只有 `src/styles/global.scss`**，内容限于 reset 和 `:root` 变量。断点、公共 mixin 放 `src/styles/_mixins.scss`——它是 partial，不产出 CSS，页面用 `@use '../styles/mixins' as *;` 引入。任何页面或组件不得 import 其它全局 css。

8. **财务前端的 theme token** 通过 `ConfigProvider` 的 `theme.token` 设置，不用 CSS 变量改 AntD 内部——两套机制并存会出现"改了没生效"。

9. **文件名全项目 kebab-case**，组件文件也是：`voucher-list.tsx` 导出 `VoucherList`。理由见 general/structure 第 2 节（Windows 大小写不敏感、Linux 敏感）。

10. **目录固定为**：

    ```
    src/
    ├── pages/  components/  services/  hooks/  utils/  types/  styles/
    ```

    不新增平级目录。确实需要时先改这份规范。

11. **路径别名 `@/` 指向 `src/`**。`vite.config.ts` 的 `resolve.alias` 与 `tsconfig.app.json` 的 `paths` 必须同时配置（只配一个，编辑器能跳但构建会失败）。

12. **HTTP 封装放 `src/services/http.ts`**，是唯一直接使用 `fetch` 的地方。各业务 service 通过它发请求，不自己写 `fetch`。token 注入、401 跳转、错误翻译都在这一层。
