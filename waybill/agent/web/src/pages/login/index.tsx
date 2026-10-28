/**
 * 登录页。
 * 内网自用，测试账号直接写在页面上——别让人猜。
 */

import { Alert, Button, Card, Form, Input, Typography } from 'antd'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { login } from '@/services/auth'
import type { UserInfo } from '@/services/auth/interface'

import styles from './index.module.scss'

interface LoginPageProps {
  onLogin: (user: UserInfo) => void
}

interface LoginForm {
  username: string
  password: string
}

const TEST_ACCOUNTS = [
  { username: 'admin', password: 'waybill2026', note: '管理员' },
  { username: 'auditor', password: 'audit2026', note: '审计员' },
]

export function LoginPage({ onLogin }: LoginPageProps) {
  const navigate = useNavigate()
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function onFinish(values: LoginForm) {
    setLoading(true)
    setError('')
    try {
      const user = await login(values)
      onLogin(user)
      navigate('/tasks', { replace: true })
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : '登录失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.page}>
      <Card className={styles.card}>
        <Typography.Title level={4} className={styles.title}>
          Waybill 控制台
        </Typography.Title>
        <Typography.Paragraph type="secondary" className={styles.subtitle}>
          执行记录与审计视图
        </Typography.Paragraph>

        {error ? <Alert type="error" message={error} className={styles.alert} /> : null}

        <Form<LoginForm> layout="vertical" onFinish={onFinish} requiredMark={false}>
          <Form.Item name="username" label="账号" rules={[{ required: true, message: '请输入账号' }]}>
            <Input autoComplete="username" placeholder="admin" />
          </Form.Item>
          <Form.Item name="password" label="口令" rules={[{ required: true, message: '请输入口令' }]}>
            <Input.Password autoComplete="current-password" placeholder="waybill2026" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={loading}>
            登录
          </Button>
        </Form>

        <div className={styles.hint}>
          <Typography.Text type="secondary">测试账号</Typography.Text>
          {TEST_ACCOUNTS.map((account) => (
            <div key={account.username} className={styles.hintRow}>
              <Typography.Text code>{account.username}</Typography.Text>
              <Typography.Text code>{account.password}</Typography.Text>
              <Typography.Text type="secondary">{account.note}</Typography.Text>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}
