/** 人工闸门接口。 */

import { get, post } from '@/services/http'
import type { GateActionResult, GateListResult } from './interface'

export async function listGate(): Promise<GateListResult> {
  return get<GateListResult>('/api/gate')
}

export async function retryTask(taskId: number): Promise<GateActionResult> {
  return post<GateActionResult>(`/api/gate/${taskId}/retry`)
}

export async function resolveTask(taskId: number, note: string): Promise<GateActionResult> {
  return post<GateActionResult>(`/api/gate/${taskId}/resolve`, { note })
}
