/** 登录接口。一个函数对应一个后端接口，不互相调用。 */

import { get, post } from '@/services/http'
import type { LoginInput, UserInfo } from './interface'

export async function login(input: LoginInput): Promise<UserInfo> {
  return post<UserInfo>('/api/auth/login', input)
}

export async function logout(): Promise<void> {
  await post<{ ok: boolean }>('/api/auth/logout')
}

export async function me(): Promise<UserInfo | null> {
  const data = await get<{ user: UserInfo | null }>('/api/auth/me')
  return data.user
}

export async function hint(): Promise<string[]> {
  const data = await get<{ users: string[] }>('/api/auth/hint')
  return data.users
}
