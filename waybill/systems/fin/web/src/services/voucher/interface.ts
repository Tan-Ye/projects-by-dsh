import type { FieldError, PageResult } from '@/types'

export interface VoucherLine {
  id: number
  voucher_id: number
  seq: number
  account_code: string
  cost_center: string
  debit_cents: number
  summary: string
}

export interface VoucherRow {
  id: number
  voucher_no: string | null
  external_ref: string
  voucher_date: string
  summary: string
  dept_code: string
  attachment_count: number
  /** draft 草稿 / pending 待审批 / submitted 已入账 / voided 已作废 */
  status: string
  created_by: string
  created_at: string
  saved_at: string | null
  submitted_at: string | null
  submitted_by: string | null
  approved_at: string | null
  approved_by: string | null
  /** 复核驳回意见 */
  review_note: string | null
}

export interface VoucherDetail extends VoucherRow {
  lines: VoucherLine[]
  errors: FieldError[]
  validated: boolean
  total_cents: number
}

export type VoucherPage = PageResult<VoucherRow>

export interface VoucherLineInput {
  account_code: string
  cost_center: string
  debit_cents: number
  summary: string
}

export interface VoucherInput {
  external_ref: string
  voucher_date: string
  summary: string
  dept_code: string
  attachment_count: number
  lines: VoucherLineInput[]
}

export interface SaveResult {
  ok: boolean
  errors: FieldError[]
}

export interface CreateResult extends SaveResult {
  id: number
}

export interface VoucherQuery {
  status?: string
  external_ref?: string
  page?: number
}
