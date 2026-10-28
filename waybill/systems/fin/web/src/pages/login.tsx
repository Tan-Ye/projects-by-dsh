import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Alert, App, Card, Input, Typography } from 'antd'

import { FinButton } from '@/components/fin-button'
import { login, persistSession } from '@/services/auth'
import { ApiError } from '@/services/http'

import styles from './login.module.scss'

export function LoginPage() {
  const navigate = useNavigate()
  const { message } = App.useApp()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit() {
    if (!username.trim() || !password) {
      setError('请填写用户名和密码')
      return
    }

    setLoading(true)
    setError(null)
    try {
      const result = await login({ username: username.trim(), password })
      persistSession(result)
      message.success(`欢迎，${result.display_name}`)
      navigate('/vouchers', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '登录失败，请稍后再试')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.wrapper}>
      <Card className={styles.card}>
        <Typography.Title level={3} className={styles.title}>
          财务仿真系统
        </Typography.Title>
        <Typography.Paragraph type="secondary" className={styles.subtitle}>
          用 maker 账号制单，用 checker 账号复核提交
        </Typography.Paragraph>

        {error && <Alert type="error" message={error} showIcon className={styles.alert} />}

        <label className={styles.label}>
          用户名
          <Input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            placeholder="maker / checker"
            autoComplete="username"
          />
        </label>

        <label className={styles.label}>
          密码
          <Input.Password
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="请输入密码"
            autoComplete="current-password"
            onPressEnter={() => void handleSubmit()}
          />
        </label>

        <FinButton
          type="primary"
          block
          loading={loading}
          loadingText="登录中…"
          onClick={() => void handleSubmit()}
        >
          登录
        </FinButton>
      </Card>
    </div>
  )
}
