/**
 * 应用外壳：登录态、路由、401 兜底。
 */

import { Spin } from 'antd'
import { useEffect, useState } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'

import { WbLayout } from '@/components/wb-layout'
import { BatchPage } from '@/pages/batches'
import { EvalPage } from '@/pages/evals'
import { GatePage } from '@/pages/gate'
import { LoginPage } from '@/pages/login'
import { RecipeListPage } from '@/pages/recipe-list'
import { RunDetailPage } from '@/pages/run-detail'
import { TaskListPage } from '@/pages/task-list'
import { me } from '@/services/auth'
import type { UserInfo } from '@/services/auth/interface'
import { UNAUTHORIZED_EVENT } from '@/services/http'

import styles from './app.module.scss'

export function App() {
  const navigate = useNavigate()
  const [user, setUser] = useState<UserInfo | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    // 只在启动时探一次登录态。以前依赖路径，每切一次页面就多一次请求。
    // /api/auth/me 未登录时返回 200 + null，所以登录页也不会刷红字。
    me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setReady(true))
  }, [])

  useEffect(() => {
    function onUnauthorized() {
      setUser(null)
      navigate('/login', { replace: true })
    }
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
  }, [navigate])

  if (!ready) {
    return (
      <div className={styles.booting}>
        <Spin />
      </div>
    )
  }

  return (
    <Routes>
      <Route path="/login" element={<LoginPage onLogin={setUser} />} />

      <Route element={user ? <WbLayout user={user} /> : <Navigate to="/login" replace />}>
        <Route path="/tasks" element={<TaskListPage />} />
        <Route path="/batches" element={<BatchPage />} />
        <Route path="/gate" element={<GatePage />} />
        <Route path="/evals" element={<EvalPage />} />
        <Route path="/runs/:id" element={<RunDetailPage />} />
        <Route path="/recipes" element={<RecipeListPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/tasks" replace />} />
    </Routes>
  )
}
