/**
 * HTTP 封装：全项目唯一直接使用 fetch 的地方。
 *
 * 职责：拼 URL、带 token、把 4xx 翻成 ApiError、401 时清会话并广播事件。
 * 不做跳转、不弹提示——那是 UI 的事（依赖方向：services 不碰 UI）。
 */

import type { ApiErrorBody, FieldError } from '@/types'

const TOKEN_KEY = 'fin_token'
const ROLE_KEY = 'fin_role'
const NAME_KEY = 'fin_name'

export const UNAUTHORIZED_EVENT = 'fin:unauthorized'

export class ApiError extends Error {
  code: string
  status: number
  errors: FieldError[]

  constructor(code: string, message: string, status: number, errors: FieldError[] = []) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.errors = errors
  }
}

export const session = {
  get token(): string | null {
    return sessionStorage.getItem(TOKEN_KEY)
  },
  get role(): string | null {
    return sessionStorage.getItem(ROLE_KEY)
  },
  get displayName(): string | null {
    return sessionStorage.getItem(NAME_KEY)
  },
  save(token: string, role: string, displayName: string): void {
    sessionStorage.setItem(TOKEN_KEY, token)
    sessionStorage.setItem(ROLE_KEY, role)
    sessionStorage.setItem(NAME_KEY, displayName)
  },
  clear(): void {
    sessionStorage.removeItem(TOKEN_KEY)
    sessionStorage.removeItem(ROLE_KEY)
    sessionStorage.removeItem(NAME_KEY)
  },
}

type Query = Record<string, string | number | undefined | null>

function withQuery(path: string, query?: Query): string {
  if (!query) return path
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== '') {
      params.set(key, String(value))
    }
  }
  const qs = params.toString()
  return qs ? `${path}?${qs}` : path
}

async function request<T>(
  path: string,
  options: { method: string; query?: Query; body?: unknown },
): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = session.token
  if (token) headers.Authorization = `Bearer ${token}`

  const resp = await fetch(`/api${withQuery(path, options.query)}`, {
    method: options.method,
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  })

  const text = await resp.text()
  // 代理返回 502 的 HTML 时不能让它变成 SyntaxError——那会掩盖真正的错误
  let body: unknown = null
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = null
    }
  }

  if (resp.status === 401) {
    session.clear()
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
  }

  if (!resp.ok) {
    const payload = body as ApiErrorBody | null
    throw new ApiError(
      payload?.code ?? 'HTTP_ERROR',
      payload?.message ?? resp.statusText,
      resp.status,
      payload?.errors ?? [],
    )
  }

  return body as T
}

export const http = {
  get<T>(path: string, query?: Query): Promise<T> {
    return request<T>(path, { method: 'GET', query })
  },
  post<T>(path: string, body?: unknown): Promise<T> {
    return request<T>(path, { method: 'POST', body })
  },
  put<T>(path: string, body?: unknown): Promise<T> {
    return request<T>(path, { method: 'PUT', body })
  },
}
