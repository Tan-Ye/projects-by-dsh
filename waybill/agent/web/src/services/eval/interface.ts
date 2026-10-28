/** 评测结果的类型。 */

export interface EvalCase {
  id: string
  name: string
  status: string
  reason_code: string | null
  passed: boolean
  problems: string[]
}

export interface EvalSummary {
  id: number
  label: string
  total: number
  passed: number
  metrics: Record<string, number>
  created_by: string
  created_at: string
}

export interface EvalDetail extends EvalSummary {
  cases: EvalCase[]
}

export interface EvalListResult {
  items: EvalSummary[]
  total: number
}
