/** 运行详情的类型。三层下钻：run → steps → 证据。 */

import type { RunStatus, StepItem } from '@/types'

export interface RunRow {
  id: number
  task_id: number | null
  task_name: string
  recipe_name: string
  recipe_version: number
  external_ref: string | null
  status: RunStatus
  reason_code: string | null
  reason_message: string | null
  started_at: string
  finished_at: string | null
}

export interface ExtractionItem {
  name: string
  payload: unknown
  sha256: string
}

export interface VerificationItem {
  layer: 'document' | 'cross_system'
  field: string
  passed: number
  reason_code: string | null
  expected: string
  actual: string
}

export interface JudgmentItem {
  summary: string
  chosen: string | null
  confidence: number | null
  rationale: string
  accepted: number
  reason: string
}

export interface RepairItem {
  step_seq: number
  target_path: string | null
  old_target: unknown
  new_target: unknown
  confidence: number | null
  rationale: string
  outcome: 'retried_ok' | 'retried_failed'
}

export interface RunDetail {
  run: RunRow
  steps: StepItem[]
  extractions: ExtractionItem[]
  verifications: VerificationItem[]
  judgments: JudgmentItem[]
  repairs: RepairItem[]
}
