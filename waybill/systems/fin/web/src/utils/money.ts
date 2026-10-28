/**
 * 金额换算。
 *
 * 全项目金额在层间传递时一律是「分」的整数，只在展示和输入这两个边界上转元。
 * 不用 `parseFloat(x) * 100`：128.60 * 100 会得到 12860.000000000002。
 */

const YUAN_PATTERN = /^\d+(\.\d{1,2})?$/

/** 元字符串 → 分。格式不合法返回 NaN，由调用方判断。 */
export function yuanToCents(input: string): number {
  const text = input.trim()
  if (!YUAN_PATTERN.test(text)) return NaN

  const [integer, fraction = ''] = text.split('.')
  return Number(integer) * 100 + Number(fraction.padEnd(2, '0'))
}

/** 分 → 元字符串，始终两位小数 */
export function centsToYuan(cents: number): string {
  return (cents / 100).toFixed(2)
}

/** 带千分位的展示形态 */
export function centsToYuanGrouped(cents: number): string {
  const [integer, fraction] = centsToYuan(cents).split('.')
  return `${integer.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}.${fraction}`
}
