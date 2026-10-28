/** 人工闸门的类型。 */

export interface GateItem {
  task_id: number
  name: string
  recipe: string
  attempts: number
  created_at: string
  last_error: string | null
  run_id: number | null
  external_ref: string | null
  reason_code: string | null
  reason_message: string | null
  finished_at: string | null
}

export interface GateListResult {
  items: GateItem[]
  total: number
}

export interface GateActionResult {
  ok: boolean
  status: string
}
