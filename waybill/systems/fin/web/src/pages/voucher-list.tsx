import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Alert, Input, Select, Space, Table, Tag, Typography } from 'antd'
import type { TableProps } from 'antd'

import { FinButton } from '@/components/fin-button'
import { currentRole } from '@/services/auth'
import { ApiError } from '@/services/http'
import { listVouchers } from '@/services/voucher'
import type { VoucherRow } from '@/services/voucher/interface'
import {
  filtersKey,
  formatDateTime,
  parseFilters,
  serializeFilters,
  statusColor,
  statusText,
} from '@/utils'
import type { ListFilters } from '@/utils'

import styles from './voucher-list.module.scss'

const PAGE_SIZE = 20

const STATUS_OPTIONS = [
  { value: '', label: '全部状态' },
  { value: 'draft', label: '草稿' },
  { value: 'pending', label: '待审批' },
  { value: 'submitted', label: '已入账' },
  { value: 'voided', label: '已作废' },
]

/**
 * 筛选条件存在 sessionStorage，不进地址栏。
 *
 * 目的是"从详情页返回时还在同一屏"，不是给别人复制链接——
 * 所以不放 URL，也不做明文展示。解析规则在 utils/filters.ts，有单测。
 */
export function VoucherListPage() {
  const role = currentRole()
  // 复核人进来第一眼就该看到待自己处理的单子
  const defaultStatus = role === 'checker' ? 'pending' : ''

  const [filters, setFilters] = useState<ListFilters>(() =>
    parseFilters(sessionStorage.getItem(filtersKey(role)), defaultStatus),
  )
  const [items, setItems] = useState<VoucherRow[]>([])
  const [total, setTotal] = useState(0)
  const [externalRef, setExternalRef] = useState(filters.external_ref)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const { status, page } = filters

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await listVouchers({
        status: filters.status,
        external_ref: filters.external_ref,
        page: filters.page,
      })
      setItems(result.items)
      setTotal(result.total)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '列表加载失败')
    } finally {
      setLoading(false)
    }
  }, [filters])

  useEffect(() => {
    sessionStorage.setItem(filtersKey(role), serializeFilters(filters))
  }, [filters, role])

  useEffect(() => {
    void load()
  }, [load])

  function applyFilters(next: Partial<ListFilters>) {
    setFilters((prev) => ({ ...prev, page: 1, ...next }))
  }

  const columns: TableProps<VoucherRow>['columns'] = [
    {
      title: '外部单号',
      dataIndex: 'external_ref',
      render: (value: string, row) => <Link to={`/vouchers/${row.id}`}>{value}</Link>,
    },
    { title: '摘要', dataIndex: 'summary' },
    { title: '部门', dataIndex: 'dept_code' },
    {
      title: '状态',
      dataIndex: 'status',
      render: (value: string, row) =>
        // 被驳回的单据退回草稿，但列表上要一眼能看出它是被退回来的
        value === 'draft' && row.review_note ? (
          <Tag color="red" title={row.review_note}>已驳回</Tag>
        ) : (
          <Tag color={statusColor(value)}>{statusText(value)}</Tag>
        ),
    },
    {
      title: '凭证号',
      dataIndex: 'voucher_no',
      render: (value: string | null) => value ?? '—',
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      render: (value: string) => formatDateTime(value),
    },
  ]

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <Typography.Title level={4} className={styles.title}>
          {role === 'checker' ? '待复核凭证' : '凭证列表'}
        </Typography.Title>
        <Link to="/vouchers/new">
          <FinButton type="primary">新建凭证</FinButton>
        </Link>
      </div>

      <Space className={styles.filters} wrap>
        <Select
          value={status}
          onChange={(value) => applyFilters({ status: value })}
          options={STATUS_OPTIONS}
          style={{ width: 140 }}
        />
        <Input
          value={externalRef}
          onChange={(event) => setExternalRef(event.target.value)}
          onPressEnter={() => applyFilters({ external_ref: externalRef.trim() })}
          placeholder="按外部单号筛选"
          allowClear
          style={{ width: 220 }}
        />
        <FinButton onClick={() => applyFilters({ external_ref: externalRef.trim() })}>
          查询
        </FinButton>
      </Space>

      {error && <Alert type="error" message={error} showIcon className={styles.alert} />}

      <Table<VoucherRow>
        rowKey="id"
        columns={columns}
        dataSource={items}
        loading={loading}
        className={styles.table}
        pagination={{
          current: page,
          pageSize: PAGE_SIZE,
          total,
          showSizeChanger: false,
          onChange: (nextPage) => setFilters((prev) => ({ ...prev, page: nextPage })),
        }}
      />
    </div>
  )
}
