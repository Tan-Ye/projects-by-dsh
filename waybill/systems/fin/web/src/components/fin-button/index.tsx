/**
 * 财务项目通用按钮。
 *
 * 可覆盖的类名：
 *   fin-btn           根
 *   fin-btn__text     按钮文字
 *   fin-btn--loading  加载态
 */

import { Button } from 'antd'
import type { ButtonProps } from 'antd'

import './index.scss'

export interface FinButtonProps extends ButtonProps {
  loadingText?: string
}

export function FinButton({ loadingText, loading, children, ...rest }: FinButtonProps) {
  const className = `fin-btn${loading ? ' fin-btn--loading' : ''}`

  return (
    <Button className={className} loading={loading} {...rest}>
      <span className="fin-btn__text">{loading && loadingText ? loadingText : children}</span>
    </Button>
  )
}
