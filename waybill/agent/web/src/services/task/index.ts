/** 任务接口。 */

import { get } from '@/services/http'
import type { TaskListResult } from './interface'

/**
 * 任务列表。
 * includeOrphans：连"没有任务归属的运行"一起列（单条调试、评测产生的）。
 * 默认不列，否则任务页会被评测记录淹掉。
 */
export async function listTasks(includeOrphans = false): Promise<TaskListResult> {
  const query = includeOrphans ? '?include_orphans=true' : ''
  return get<TaskListResult>(`/api/tasks${query}`)
}
