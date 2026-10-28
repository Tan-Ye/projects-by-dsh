import assert from 'node:assert/strict'
import test from 'node:test'

/** 内存版 sessionStorage：让 http 层脱离浏览器也能测 */
class MemoryStorage {
  private map = new Map<string, string>()

  get length(): number {
    return this.map.size
  }
  getItem(key: string): string | null {
    return this.map.get(key) ?? null
  }
  setItem(key: string, value: string): void {
    this.map.set(key, value)
  }
  removeItem(key: string): void {
    this.map.delete(key)
  }
  key(index: number): string | null {
    return [...this.map.keys()][index] ?? null
  }
  clear(): void {
    this.map.clear()
  }
}

const storage = new MemoryStorage()
const events: string[] = []

Object.assign(globalThis, {
  sessionStorage: storage,
  window: { dispatchEvent: (event: { type: string }) => events.push(event.type) },
})

const { ApiError, UNAUTHORIZED_EVENT, http, session } = await import(
  '../src/services/http.ts'
)

interface Captured {
  url: string
  init: RequestInit
}

function stubFetch(handler: (captured: Captured) => Response): Captured[] {
  const calls: Captured[] = []
  Object.assign(globalThis, {
    fetch: async (url: string, init: RequestInit) => {
      const captured = { url, init }
      calls.push(captured)
      return handler(captured)
    },
  })
  return calls
}

function reset(): void {
  storage.clear()
  events.length = 0
}

test('有 token 时自动带 Authorization 头', async () => {
  reset()
  session.save('abc123', 'maker', '张制单')
  const calls = stubFetch(() => new Response('{}', { status: 200 }))

  await http.get('/vouchers')

  const headers = calls[0].init.headers as Record<string, string>
  assert.equal(headers.Authorization, 'Bearer abc123')
  assert.equal(calls[0].url, '/api/vouchers')
})

test('没有 token 时不带 Authorization 头', async () => {
  reset()
  const calls = stubFetch(() => new Response('{}', { status: 200 }))

  await http.get('/vouchers')

  const headers = calls[0].init.headers as Record<string, string>
  assert.equal(headers.Authorization, undefined)
})

test('查询参数跳过空值并做 URL 编码', async () => {
  reset()
  const calls = stubFetch(() => new Response('{}', { status: 200 }))

  await http.get('/vouchers', { status: '', page: 2, external_ref: 'BX 2024', x: undefined })

  assert.equal(calls[0].url, '/api/vouchers?page=2&external_ref=BX+2024')
})

test('200 返回解析后的 JSON', async () => {
  reset()
  stubFetch(() => new Response(JSON.stringify({ id: 7 }), { status: 200 }))

  const result = await http.get<{ id: number }>('/vouchers/7')

  assert.deepEqual(result, { id: 7 })
})

test('空 body 返回 null，不抛异常', async () => {
  reset()
  stubFetch(() => new Response('', { status: 200 }))

  assert.equal(await http.post('/vouchers/7/submit'), null)
})

test('4xx 把后端错误翻成 ApiError', async () => {
  reset()
  stubFetch(
    () =>
      new Response(
        JSON.stringify({
          code: 'DUPLICATE_DOC',
          message: '外部单号已存在',
          errors: [{ field: 'external_ref', code: 'DUP', message: '重复' }],
        }),
        { status: 409 },
      ),
  )

  await assert.rejects(
    () => http.post('/vouchers', {}),
    (error: unknown) => {
      assert.ok(error instanceof ApiError)
      assert.equal(error.code, 'DUPLICATE_DOC')
      assert.equal(error.status, 409)
      assert.equal(error.message, '外部单号已存在')
      assert.equal(error.errors.length, 1)
      return true
    },
  )
})

test('4xx 返回非 JSON 时兜底成 HTTP_ERROR', async () => {
  reset()
  stubFetch(() => new Response('<html>Bad Gateway</html>', { status: 502 }))

  await assert.rejects(
    () => http.get('/vouchers'),
    (error: unknown) => {
      assert.ok(error instanceof ApiError)
      assert.equal(error.code, 'HTTP_ERROR')
      assert.equal(error.status, 502)
      return true
    },
  )
})

test('401 清掉会话并广播事件', async () => {
  reset()
  session.save('stale', 'maker', '张制单')
  stubFetch(() => new Response(JSON.stringify({ code: 'TOKEN_EXPIRED' }), { status: 401 }))

  await assert.rejects(() => http.get('/vouchers'))

  assert.equal(session.token, null)
  assert.deepEqual(events, [UNAUTHORIZED_EVENT])
})

test('session 三个字段一起生死', () => {
  reset()
  session.save('t', 'checker', '李复核')
  assert.equal(session.role, 'checker')
  assert.equal(session.displayName, '李复核')

  session.clear()
  assert.equal(session.token, null)
  assert.equal(session.role, null)
  assert.equal(session.displayName, null)
})
