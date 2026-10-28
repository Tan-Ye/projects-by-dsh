import { http, session } from '@/services/http'

import type { LoginRequest, LoginResponse } from './interface'

export function login(payload: LoginRequest): Promise<LoginResponse> {
  return http.post<LoginResponse>('/login', payload)
}

/** 登录成功后把会话存起来，auth 模块独占 sessionStorage 的写入 */
export function persistSession(result: LoginResponse): void {
  // 换账号后不该继承上一个人的筛选条件
  clearListFilters()
  session.save(result.token, result.role, result.display_name)
}

export function logout(): void {
  clearListFilters()
  session.clear()
}

/** 列表筛选按角色分开存，退出登录时一并清掉 */
function clearListFilters(): void {
  for (const key of Object.keys(sessionStorage)) {
    if (key.startsWith('fin_voucher_filters_')) sessionStorage.removeItem(key)
  }
}

export function currentRole(): string | null {
  return session.role
}

export function currentDisplayName(): string | null {
  return session.displayName
}
