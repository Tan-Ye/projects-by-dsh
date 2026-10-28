/** 科目缺口的类型。 */

export interface GapItem {
  summary: string
  count: number
  last_at: string
  rationale: string
  reason: string
}

export interface GapListResult {
  items: GapItem[]
  total: number
  affected: number
}
