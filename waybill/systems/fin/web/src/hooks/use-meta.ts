/**
 * 元数据：科目树 + 部门。
 *
 * 两个接口一起用，属于「多接口协调」，所以放 hook 而不是 services——
 * services 一个函数只对应一个后端接口。
 */

import { useEffect, useState } from 'react'

import { getAccounts, getDepartments } from '@/services/meta'
import type { AccountNode, Department } from '@/services/meta/interface'

export interface MetaState {
  accounts: AccountNode[]
  departments: Department[]
  loading: boolean
  error: string | null
}

export function useMeta(): MetaState {
  const [accounts, setAccounts] = useState<AccountNode[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoading(true)
      setError(null)
      try {
        const [accountList, departmentList] = await Promise.all([
          getAccounts(),
          getDepartments(),
        ])
        if (cancelled) return
        setAccounts(accountList)
        setDepartments(departmentList)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : '元数据加载失败')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [])

  return { accounts, departments, loading, error }
}
