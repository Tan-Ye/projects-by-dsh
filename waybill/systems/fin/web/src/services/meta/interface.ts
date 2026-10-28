/** 科目节点：后端返回的就是嵌套树，children 已经组装好 */
export interface AccountNode {
  code: string
  name: string
  parent_code: string | null
  level: number
  is_leaf: number
  is_active: number
  sort: number
  children: AccountNode[]
}

export interface Department {
  code: string
  name: string
  is_active: number
}

export interface CostCenter {
  code: string
  name: string
  dept_code: string
  is_default: number
  is_active: number
}
