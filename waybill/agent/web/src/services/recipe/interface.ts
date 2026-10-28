/** 配方列表的类型。 */

export interface RecipeItem {
  name: string
  version: number
  base_url: string
  steps: number
  requires: string[]
  repairs: number
  repaired_ok: number
  last_repair_at: string | null
}

export interface RecipeListResult {
  items: RecipeItem[]
  total: number
}
