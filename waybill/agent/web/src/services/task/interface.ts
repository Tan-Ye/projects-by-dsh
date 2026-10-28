/** 任务列表的类型。 */

import type { RunStatus } from '@/types'

export interface TaskItem {
  task_id: number | null
  name: string
  recipe: string
  status: RunStatus
  attempts: number
  created_at: string
  finished_at: string | null
  last_error: string | null
  run_id: number | null
  external_ref: string | null
  reason_code: string | null
  reason_message: string | null
  recipe_version: number | null
}

export interface TaskListResult {
  items: TaskItem[]
  total: number
}
