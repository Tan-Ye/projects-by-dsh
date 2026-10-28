/**
 * WbLayout · 控制台外壳
 *
 * 可覆盖的类名：
 *   .wb-layout        根容器
 *   .wb-layout-sider  侧栏
 *   .wb-layout-header 顶栏
 *   .wb-layout-user   用户区
 */

import { Button, Layout, Menu, Space, Typography } from 'antd'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'

import { logout } from '@/services/auth'
import type { UserInfo } from '@/services/auth/interface'

import './index.scss'

const { Header, Sider, Content } = Layout

interface WbLayoutProps {
  user: UserInfo | null
}

const MENU = [
  { key: '/tasks', label: <Link to="/tasks">任务</Link> },
  { key: '/batches', label: <Link to="/batches">批次</Link> },
  { key: '/gate', label: <Link to="/gate">人工闸门</Link> },
  { key: '/evals', label: <Link to="/evals">评测</Link> },
  { key: '/recipes', label: <Link to="/recipes">配方</Link> },
]

export function WbLayout({ user }: WbLayoutProps) {
  const location = useLocation()
  const navigate = useNavigate()

  const selected = MENU.find((item) => location.pathname.startsWith(item.key))?.key ?? '/tasks'

  async function onLogout() {
    try {
      await logout()
    } finally {
      navigate('/login', { replace: true })
    }
  }

  return (
    <Layout className="wb-layout">
      <Sider className="wb-layout-sider" width={200} theme="light">
        <div className="wb-layout-brand">Waybill</div>
        <Menu mode="inline" selectedKeys={[selected]} items={MENU} />
      </Sider>
      <Layout>
        <Header className="wb-layout-header">
          <Space className="wb-layout-user">
            <Typography.Text type="secondary">{user?.display ?? ''}</Typography.Text>
            <Button size="small" onClick={onLogout}>
              退出
            </Button>
          </Space>
        </Header>
        <Content className="wb-layout-content">
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
