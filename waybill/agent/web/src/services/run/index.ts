/** 运行详情接口。 */

import { get } from '@/services/http'
import type { RunDetail } from './interface'

export async function getRun(runId: number): Promise<RunDetail> {
  return get<RunDetail>(`/api/runs/${runId}`)
}
