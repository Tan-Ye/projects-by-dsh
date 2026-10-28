/**
 * 列表筛选条件的序列化。
 *
 * 只做"字符串 ↔ 对象"的纯转换，读写 sessionStorage 交给页面——
 * 这样逻辑可以脱离浏览器单测。
 */

export interface ListFilters {
  status: string
  external_ref: string
  page: number
}

/** 按角色分开存：制单人和复核人的筛选互不干扰 */
export function filtersKey(role: string | null): string {
  return `fin_voucher_filters_${role ?? 'anonymous'}`
}

export function defaultFilters(defaultStatus: string): ListFilters {
  return { status: defaultStatus, external_ref: '', page: 1 }
}

/** 存坏了就退回默认值，不能让列表打不开 */
export function parseFilters(raw: string | null, defaultStatus: string): ListFilters {
  const fallback = defaultFilters(defaultStatus)
  if (!raw) return fallback

  try {
    const parsed = JSON.parse(raw) as Partial<ListFilters>
    const page = parsed.page
    return {
      status: typeof parsed.status === 'string' ? parsed.status : fallback.status,
      external_ref: typeof parsed.external_ref === 'string' ? parsed.external_ref : '',
      page: Number.isInteger(page) && (page as number) > 0 ? (page as number) : 1,
    }
  } catch {
    return fallback
  }
}

export function serializeFilters(filters: ListFilters): string {
  return JSON.stringify({
    status: filters.status,
    external_ref: filters.external_ref,
    page: filters.page,
  })
}
