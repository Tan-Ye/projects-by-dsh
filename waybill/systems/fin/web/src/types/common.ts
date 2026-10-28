/** 跨模块共享的类型。只被一个 service 用的请求/响应类型不进这里。 */

export interface FieldError {
  field: string
  code: string
  message: string
}

export interface PageResult<T> {
  total: number
  page: number
  page_size: number
  items: T[]
}

/** 后端 4xx 的响应体 */
export interface ApiErrorBody {
  code: string
  message: string
  errors?: FieldError[]
}
