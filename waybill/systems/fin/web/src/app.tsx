import { useEffect } from 'react'
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { Layout, Space, Tag, Typography } from 'antd'

import { FinButton } from '@/components/fin-button'
import { currentDisplayName, currentRole, logout } from '@/services/auth'
import { UNAUTHORIZED_EVENT, session } from '@/services/http'
import { LoginPage } from './pages/login'
import { VoucherEditPage } from './pages/voucher-edit'
import { VoucherListPage } from './pages/voucher-list'

import './app.scss'

const { Header, Content } = Layout

export function App() {
  const location = useLocation()
  const navigate = useNavigate()
  const isLogin = location.pathname === '/login'
  const authenticated = session.token !== null

  // http 层只清会话、广播事件；跳到哪由 UI 决定
  useEffect(() => {
    function onUnauthorized() {
      navigate('/login', { replace: true })
    }
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
  }, [navigate])

  if (!authenticated && !isLogin) {
    return <Navigate to="/login" replace />
  }

  if (isLogin) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
      </Routes>
    )
  }

  return (
    <Layout className="fin-layout">
      <Header className="fin-header">
        <Space size="large">
          <Typography.Text strong>财务仿真系统</Typography.Text>
          <Link to="/vouchers">凭证列表</Link>
          <Link to="/vouchers/new">新建凭证</Link>
        </Space>

        <Space>
          <Tag>{currentRole() === 'checker' ? '复核' : '制单'}</Tag>
          <span className="fin-header__user">{currentDisplayName() ?? ''}</span>
          <FinButton
            size="small"
            onClick={() => {
              logout()
              navigate('/login', { replace: true })
            }}
          >
            退出
          </FinButton>
        </Space>
      </Header>

      <Content className="fin-content">
        <Routes>
          <Route path="/vouchers" element={<VoucherListPage />} />
          <Route path="/vouchers/new" element={<VoucherEditPage />} />
          <Route path="/vouchers/:id" element={<VoucherEditPage />} />
          <Route path="*" element={<Navigate to="/vouchers" replace />} />
        </Routes>
      </Content>
    </Layout>
  )
}
