/** 跨模块共用的类型。 */

/** 任务与运行的终态。resolved = 人处理完了（agent 没跑成功，人接手）。 */
export type RunStatus =
  | 'pending'
  | 'running'
  | 'succeeded'
  | 'waiting_human'
  | 'failed'
  | 'resolved'

/** 步骤执行结果。 */
export interface StepItem {
  seq: number
  intent: string
  action: string
  outcome: 'ok' | 'failed'
  reason_code: string | null
  reason_message: string | null
  target_path: string | null
  duration_ms: number
}
