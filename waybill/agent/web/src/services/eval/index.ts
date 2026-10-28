/** 评测结果接口。 */

import { get } from '@/services/http'
import type { EvalDetail, EvalListResult } from './interface'

export async function listEvals(): Promise<EvalListResult> {
  return get<EvalListResult>('/api/evals')
}

export async function getEval(evalId: number): Promise<EvalDetail> {
  return get<EvalDetail>(`/api/evals/${evalId}`)
}
