/** 批次接口。启动是异步的：返回 batch_id，进程在后台跑。 */

import { get, post } from '@/services/http'
import type {
  BatchDetailResult,
  BatchListResult,
  BatchOptions,
  BatchStartInput,
} from './interface'

export async function listBatches(): Promise<BatchListResult> {
  return get<BatchListResult>('/api/batches')
}

export async function getBatch(batchId: number): Promise<BatchDetailResult> {
  return get<BatchDetailResult>(`/api/batches/${batchId}`)
}

export async function startBatch(input: BatchStartInput): Promise<{ batch_id: number }> {
  return post<{ batch_id: number }>('/api/batches', input)
}

export async function batchOptions(): Promise<BatchOptions> {
  return get<BatchOptions>('/api/batches/meta/options')
}
