/**
 * 任务列表。
 * 一条记录 = 一个任务 + 它最近一次运行；没有任务归属的运行也列出来。
 */

import { Alert, Card, Input, Segmented, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { WbStatusTag } from '@/components/wb-status-tag'
import { listTasks } from '@/services/task'
import type { TaskItem } from '@/services/task/interface'

import styles from './index.module.scss'

type Filter = '全部' | '成功' | '待人工' | '失败'

const FILTERS: Filter[] = ['全部', '成功', '待人工', '失败']

const FILTER_STATUS: Record<Filter, string | null> = {
  全部: null,
  成功: 'succeeded',
  待人工: 'waiting_human',
  失败: 'failed',
}

export function TaskListPage() {
  const navigate = useNavigate()
  const [items, setItems] = useState<TaskItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [keyword, setKeyword] = useState('')
  const [filter, setFilter] = useState<Filter>('全部')
  const [showAll, setShowAll] = useState(false)

  useEffect(() => {
    setLoading(true)
    listTasks(showAll)
      .then((data) => setItems(data.items))
      .catch((exc: unknown) => setError(exc instanceof Error ? exc.message : '加载失败'))
      .finally(() => setLoading(false))
  }, [showAll])

  const rows = useMemo(() => {
    const status = FILTER_STATUS[filter]
    const text = keyword.trim().toLowerCase()
    return items.filter((item) => {
      if (status && item.status !== status) return false
      if (!text) return true
      return [item.name, item.external_ref, item.reason_code]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(text))
    })
  }, [items, filter, keyword])

  const columns: ColumnsType<TaskItem> = [
    {
      title: '单号',
      dataIndex: 'external_ref',
      key: 'external_ref',
      width: 160,
      render: (value: string | null) => value ?? <Typography.Text type="secondary">-</Typography.Text>,
    },
    { title: '任务', dataIndex: 'name', key: 'name', ellipsis: true },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (value: TaskItem['status']) => <WbStatusTag status={value} />,
    },
    {
      title: '原因码',
      dataIndex: 'reason_code',
      key: 'reason_code',
      width: 180,
      render: (value: string | null) =>
        value ? <Tag color="orange">{value}</Tag> : <Typography.Text type="secondary">-</Typography.Text>,
    },
    {
      title: '配方',
      dataIndex: 'recipe',
      key: 'recipe',
      width: 180,
      render: (_: string, row: TaskItem) =>
        row.recipe_version ? `${row.recipe} v${row.recipe_version}` : row.recipe,
    },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 180 },
  ]

  return (
    <div className={styles.page}>
      <Card className={styles.toolbar} size="small">
        <Space wrap>
          <Segmented options={FILTERS} value={filter} onChange={(value) => setFilter(value as Filter)} />
          <Input.Search
            allowClear
            placeholder="搜单号 / 任务名 / 原因码"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            className={styles.search}
          />
          <Segmented
            options={['业务任务', '全部运行']}
            value={showAll ? '全部运行' : '业务任务'}
            onChange={(value) => setShowAll(value === '全部运行')}
          />
          <Typography.Text type="secondary">共 {rows.length} 条</Typography.Text>
        </Space>
      </Card>

      {error ? <Alert type="error" message={error} className={styles.alert} /> : null}

      <Card size="small" className={styles.tableCard}>
        <Table<TaskItem>
          rowKey={(row) => `${row.task_id ?? 'run'}-${row.run_id ?? row.name}`}
          size="small"
          loading={loading}
          columns={columns}
          dataSource={rows}
          pagination={{ pageSize: 15, showSizeChanger: false }}
          onRow={(row) => ({
            onClick: () => {
              if (row.run_id) navigate(`/runs/${row.run_id}`)
            },
            className: row.run_id ? styles.clickableRow : undefined,
          })}
        />
      </Card>
    </div>
  )
}
