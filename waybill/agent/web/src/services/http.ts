/**
 * HTTP 封装：全项目唯一直接使用 fetch 的地方。
 *
 * 职责：拼请求、把非 2xx 翻成 ApiError、401 时广播事件。
 * 不做跳转、不弹提示——那是 UI 的事（依赖方向：services 不碰 UI）。
 */

export const UNAUTHORIZED_EVENT = 'wb:unauthorized'

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, options: { method: string; body?: unknown }): Promise<T> {
  const resp = await fetch(path, {
    method: options.method,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  })

  const text = await resp.text()
  // 代理返回的 HTML 不能让它变成 SyntaxError——那会掩盖真正的错误
  let body: unknown = null
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = null
    }
  }

  if (resp.status === 401 && path !== '/api/auth/login') {
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
  }

  if (!resp.ok) {
    const detail = (body as { detail?: string } | null)?.detail
    throw new ApiError(detail ?? resp.statusText ?? '请求失败', resp.status)
  }

  return body as T
}

export function get<T>(path: string): Promise<T> {
  return request<T>(path, { method: 'GET' })
}

export function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, { method: 'POST', body })
}
