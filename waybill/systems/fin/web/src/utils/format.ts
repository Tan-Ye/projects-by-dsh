/** 展示用的格式化。全项目统一，不为个别地方加开关——特例在使用处单独处理。 */

const STATUS_TEXT: Record<string, string> = {
  draft: '草稿',
  pending: '待审批',
  submitted: '已入账',
  voided: '已作废',
}

const STATUS_COLOR: Record<string, string> = {
  draft: 'default',
  pending: 'gold',
  submitted: 'green',
  voided: 'red',
}

export function statusText(status: string): string {
  return STATUS_TEXT[status] ?? status
}

export function statusColor(status: string): string {
  return STATUS_COLOR[status] ?? 'default'
}

/** 后端时间是 `YYYY-MM-DD HH:MM:SS`，原样展示，只处理空值 */
export function formatDateTime(value: string | null): string {
  return value ? value.slice(0, 16) : '—'
}

/** 拼接口路径里用，避免各处手动判断 */
export function parsePositiveInt(value: string | undefined): number | null {
  if (!value) return null
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}
