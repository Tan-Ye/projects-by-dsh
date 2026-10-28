import { http } from '@/services/http'

import type {
  CreateResult,
  SaveResult,
  VoucherDetail,
  VoucherInput,
  VoucherPage,
  VoucherQuery,
} from './interface'

export function listVouchers(query: VoucherQuery): Promise<VoucherPage> {
  return http.get<VoucherPage>('/vouchers', {
    status: query.status,
    external_ref: query.external_ref,
    page: query.page,
  })
}

export function getVoucher(id: number): Promise<VoucherDetail> {
  return http.get<VoucherDetail>(`/vouchers/${id}`)
}

export function createVoucher(data: VoucherInput): Promise<CreateResult> {
  return http.post<CreateResult>('/vouchers', data)
}

export function saveVoucher(id: number, data: VoucherInput): Promise<SaveResult> {
  return http.put<SaveResult>(`/vouchers/${id}`, data)
}

/** 制单人提交审批：draft → pending */
export function submitVoucher(id: number): Promise<VoucherDetail> {
  return http.post<VoucherDetail>(`/vouchers/${id}/submit`)
}

/** 复核通过并入账：pending → submitted（仅 checker） */
export function approveVoucher(id: number): Promise<VoucherDetail> {
  return http.post<VoucherDetail>(`/vouchers/${id}/approve`)
}

/** 复核驳回：pending → draft（仅 checker） */
export function rejectVoucher(id: number, note: string): Promise<VoucherDetail> {
  return http.post<VoucherDetail>(`/vouchers/${id}/reject`, { note })
}
