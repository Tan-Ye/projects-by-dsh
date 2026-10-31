/**
 * WbStatusTag · 任务/运行状态标签
 *
 * 可覆盖的类名：
 *   .wb-status-tag            根元素
 *   .wb-status-tag.is-success  成功
 *   .wb-status-tag.is-warn     待人工
 *   .wb-status-tag.is-error    失败
 *   .wb-status-tag.is-idle     未开始 / 运行中
 */

import { Tag } from 'antd'

import type { RunStatus } from '@/types'

import './index.scss'

const MAP: Record<string, { text: string; color: string; tone: string }> = {
  succeeded: { text: '已完成', color: 'success', tone: 'success' },
  waiting_human: { text: '待人工', color: 'warning', tone: 'warn' },
  failed: { text: '失败', color: 'error', tone: 'error' },
  resolved: { text: '已处理', color: 'default', tone: 'idle' },
  aborted: { text: '已中止', color: 'default', tone: 'idle' },
  running: { text: '运行中', color: 'processing', tone: 'idle' },
  pending: { text: '排队中', color: 'default', tone: 'idle' },
}

interface WbStatusTagProps {
  status: RunStatus
}

export function WbStatusTag({ status }: WbStatusTagProps) {
  const conf = MAP[status] ?? { text: status, color: 'default', tone: 'idle' }
  return (
    <Tag className={`wb-status-tag is-${conf.tone}`} color={conf.color}>
      {conf.text}
    </Tag>
  )
}
