/** 任务接口。 */

import { get } from '@/services/http'
import type { TaskListResult } from './interface'

export async function listTasks(): Promise<TaskListResult> {
  return get<TaskListResult>('/api/tasks')
}
