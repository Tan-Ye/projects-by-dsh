/**
 * 配方列表：文件是真相，自愈历史在库里。
 */

import { Alert, Card, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useEffect, useState } from 'react'

import { listRecipes } from '@/services/recipe'
import type { RecipeItem } from '@/services/recipe/interface'

import styles from './index.module.scss'

export function RecipeListPage() {
  const [items, setItems] = useState<RecipeItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    listRecipes()
      .then((data) => setItems(data.items))
      .catch((exc: unknown) => setError(exc instanceof Error ? exc.message : '加载失败'))
      .finally(() => setLoading(false))
  }, [])

  const columns: ColumnsType<RecipeItem> = [
    { title: '配方', dataIndex: 'name', key: 'name' },
    { title: '版本', dataIndex: 'version', key: 'version', width: 80, render: (value: number) => `v${value}` },
    { title: '步骤数', dataIndex: 'steps', key: 'steps', width: 90 },
    {
      title: '参数',
      dataIndex: 'requires',
      key: 'requires',
      render: (value: string[]) => (value.length ? value.join(' / ') : '-'),
    },
    {
      title: '自愈次数',
      dataIndex: 'repairs',
      key: 'repairs',
      width: 110,
      render: (value: number, row: RecipeItem) =>
        value ? <Tag color={row.repaired_ok === value ? 'success' : 'warning'}>{value}</Tag> : '-',
    },
    {
      title: '最近自愈',
      dataIndex: 'last_repair_at',
      key: 'last_repair_at',
      width: 180,
      render: (value: string | null) => value ?? '-',
    },
  ]

  return (
    <div className={styles.page}>
      {error ? <Alert type="error" message={error} /> : null}

      <Card size="small" className={styles.card}>
        <Typography.Paragraph type="secondary">
          配方以文件为准（git 存历史）。自愈成功后 agent 会回写文件并升版本。
        </Typography.Paragraph>
        <Table<RecipeItem>
          rowKey="name"
          size="small"
          loading={loading}
          columns={columns}
          dataSource={items}
          pagination={false}
        />
      </Card>
    </div>
  )
}
