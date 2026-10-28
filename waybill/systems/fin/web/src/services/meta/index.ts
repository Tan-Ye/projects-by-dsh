import { http } from '@/services/http'

import type { AccountNode, CostCenter, Department } from './interface'

export function getAccounts(): Promise<AccountNode[]> {
  return http.get<AccountNode[]>('/meta/accounts')
}

export function getDepartments(): Promise<Department[]> {
  return http.get<Department[]>('/meta/departments')
}

export function getCostCenters(dept: string): Promise<CostCenter[]> {
  return http.get<CostCenter[]>('/meta/cost-centers', { dept })
}
