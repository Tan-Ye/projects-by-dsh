/** 批次的类型。 */

export type BatchStatus = 'running' | 'succeeded' | 'failed' | 'aborted'

export type BatchOutcome =
  | 'queued'
  | 'duplicate'
  | 'existing'
  | 'succeeded'
  | 'waiting_human'
  | 'failed'

export interface BatchItem {
  doc_no: string
  outcome: BatchOutcome
  task_id: number | null
  note: string
  created_at: string
}

export interface Batch {
  id: number
  name: string
  oa_username: string
  status_filter: string
  max_scan: number
  scanned: number
  duplicated: number
  skipped: number
  queued: number
  status: BatchStatus
  reason_code: string | null
  reason_message: string | null
  created_by: string
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface BatchListResult {
  items: Batch[]
  total: number
}

export interface BatchDetailResult {
  batch: Batch
  items: BatchItem[]
}

export interface BatchStartInput {
  username: string
  password: string
  status_filter: string
  max_scan: number
}

export interface StatusOption {
  value: string
  label: string
}

export interface BatchOptions {
  statuses: StatusOption[]
  default_user: string
}
