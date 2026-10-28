/** 科目缺口接口。 */

import { get } from '@/services/http'
import type { GapListResult } from './interface'

export async function listGaps(): Promise<GapListResult> {
  return get<GapListResult>('/api/gaps')
}
