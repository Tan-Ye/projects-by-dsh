/**
 * 批次：启动一次"登录 → 扫描 → 逐单处理"，以及查看历史。
 *
 * 凭据只在这里填一次、随请求发给后端，由后端放进内存跑完就丢。
 * 表单值缓存在 sessionStorage：同一标签页刷新不丢，关掉页面就清。
 */

import {
  Alert,
  App,
  Button,
  Card,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useState } from 'react'

import { WbStatusTag } from '@/components/wb-status-tag'
import { batchOptions, getBatch, listBatches, startBatch } from '@/services/batch'
import type {
  Batch,
  BatchDetailResult,
  BatchItem,
  BatchOutcome,
  BatchStatus,
  StatusOption,
} from '@/services/batch/interface'

import styles from './index.module.scss'

const FORM_CACHE_KEY = 'wb:batch-form'

interface BatchForm {
  username: string
  password: string
  status_filter: string
  max_scan: number
}

// 批次状态和任务状态共用一套标签
const BATCH_STATUS: Record<BatchStatus, 'running' | 'succeeded' | 'failed'> = {
  running: 'running',
  succeeded: 'succeeded',
  failed: 'failed',
  aborted: 'failed',
}

const OUTCOME_TAG: Record<BatchOutcome, { color: string; text: string }> = {
  queued: { color: 'default', text: '已入队' },
  duplicate: { color: 'default', text: '重复' },
  existing: { color: 'default', text: '财务已有' },
  succeeded: { color: 'success', text: '成功' },
  waiting_human: { color: 'warning', text: '待人工' },
  failed: { color: 'error', text: '失败' },
}

function readCachedForm(): Partial<BatchForm> {
  try {
    const raw = sessionStorage.getItem(FORM_CACHE_KEY)
    return raw ? (JSON.parse(raw) as Partial<BatchForm>) : {}
  } catch {
    return {}
  }
}

export function BatchPage() {
  const { message } = App.useApp()
  const [batches, setBatches] = useState<Batch[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [statuses, setStatuses] = useState<StatusOption[]>([])
  const [startOpen, setStartOpen] = useState(false)
  const [starting, setStarting] = useState(false)
  const [form] = Form.useForm<BatchForm>()

  const [detail, setDetail] = useState<BatchDetailResult | null>(null)

  const refresh = useCallback(async () => {
    try {
      const data = await listBatches()
      setBatches(data.items)
      setError('')
      return data.items
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : '加载失败')
      return []
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
    batchOptions()
      .then((data) => setStatuses(data.statuses))
      .catch(() => setStatuses([{ value: '', label: '全部' }]))
  }, [refresh])

  // 有批次在跑就轮询，让页面跟上进度
  useEffect(() => {
    const running = batches.some((batch) => batch.status === 'running')
    if (!running) return
    const timer = window.setInterval(() => {
      void refresh()
    }, 2000)
    return () => window.clearInterval(timer)
  }, [batches, refresh])

  function openStart() {
    const cached = readCachedForm()
    form.setFieldsValue({
      username: cached.username ?? '',
      password: cached.password ?? '',
      status_filter: cached.status_filter ?? '',
      max_scan: cached.max_scan ?? 5,
    })
    setStartOpen(true)
  }

  async function onStart() {
    const values = await form.validateFields()
    setStarting(true)
    try {
      const { batch_id } = await startBatch(values)
      sessionStorage.setItem(FORM_CACHE_KEY, JSON.stringify(values))
      message.success(`批次 ${batch_id} 已启动`)
      setStartOpen(false)
      await refresh()
    } catch (exc) {
      message.error(exc instanceof Error ? exc.message : '启动失败')
    } finally {
      setStarting(false)
    }
  }

  async function openDetail(batchId: number) {
    try {
      setDetail(await getBatch(batchId))
    } catch (exc) {
      message.error(exc instanceof Error ? exc.message : '加载失败')
    }
  }

  const columns: ColumnsType<Batch> = [
    { title: '#', dataIndex: 'id', key: 'id', width: 64 },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (value: BatchStatus) => <WbStatusTag status={BATCH_STATUS[value]} />,
    },
    { title: '筛选', dataIndex: 'status_filter', key: 'status_filter', width: 110,
      render: (value: string) => value || '全部' },
    { title: 'OA 账号', dataIndex: 'oa_username', key: 'oa_username', width: 130 },
    {
      title: '扫描 / 重复 / 已有 / 入队',
      key: 'counts',
      render: (_: unknown, row: Batch) =>
        `${row.scanned} / ${row.duplicated} / ${row.skipped} / ${row.queued}`,
    },
    { title: '启动人', dataIndex: 'created_by', key: 'created_by', width: 110 },
    { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 180 },
    {
      title: '操作',
      key: 'actions',
      width: 90,
      render: (_: unknown, row: Batch) => (
        <Button size="small" onClick={() => openDetail(row.id)}>
          明细
        </Button>
      ),
    },
  ]

  const itemColumns: ColumnsType<BatchItem> = [
    { title: '单号', dataIndex: 'doc_no', key: 'doc_no', width: 150 },
    {
      title: '结果',
      dataIndex: 'outcome',
      key: 'outcome',
      width: 110,
      render: (value: BatchOutcome) => (
        <Tag color={OUTCOME_TAG[value].color}>{OUTCOME_TAG[value].text}</Tag>
      ),
    },
    { title: '说明', dataIndex: 'note', key: 'note', ellipsis: true },
  ]

  const openDetailBatch = detail?.batch

  return (
    <div className={styles.page}>
      <Card size="small" className={styles.card}>
        <div className={styles.toolbar}>
          <Typography.Text type="secondary">
            一次批次 = 用指定 OA 账号登录一次，扫一批单号，逐个读取并建单。财务里已有的单号会跳过。
          </Typography.Text>
          <Button type="primary" onClick={openStart}>
            启动批次
          </Button>
        </div>

        {error ? <Alert type="error" message={error} /> : null}

        <Table<Batch>
          rowKey="id"
          size="small"
          loading={loading}
          columns={columns}
          dataSource={batches}
          pagination={{ pageSize: 10, showSizeChanger: false }}
        />
      </Card>

      <Modal
        open={startOpen}
        title="启动批次"
        okText="启动"
        cancelText="取消"
        confirmLoading={starting}
        onOk={onStart}
        onCancel={() => setStartOpen(false)}
      >
        <Typography.Paragraph type="secondary">
          OA 账号只用于这次登录，不写库、不进日志。表单值留在本标签页，关掉页面即清。
        </Typography.Paragraph>
        <Form form={form} layout="vertical" requiredMark={false}>
          <Form.Item
            name="username"
            label="OA 账号"
            rules={[{ required: true, message: '请输入 OA 账号' }]}
          >
            <Input placeholder="zhangwei" autoComplete="off" />
          </Form.Item>
          <Form.Item
            name="password"
            label="OA 口令"
            rules={[{ required: true, message: '请输入 OA 口令' }]}
          >
            <Input.Password autoComplete="off" />
          </Form.Item>
          <Space size={16}>
            <Form.Item name="status_filter" label="列表筛选">
              <Select
                style={{ width: 140 }}
                options={statuses.map((item) => ({ value: item.value, label: item.label }))}
              />
            </Form.Item>
            <Form.Item name="max_scan" label="最多扫描">
              <InputNumber min={1} max={200} style={{ width: 120 }} />
            </Form.Item>
          </Space>
        </Form>
      </Modal>

      <Drawer
        open={detail !== null}
        width={720}
        title={`批次 ${openDetailBatch?.id ?? ''}`}
        onClose={() => setDetail(null)}
      >
        {openDetailBatch ? (
          <>
            <Typography.Paragraph type="secondary">
              {openDetailBatch.name} · 账号 {openDetailBatch.oa_username} · 上限{' '}
              {openDetailBatch.max_scan} 条
            </Typography.Paragraph>
            <Typography.Paragraph>
              扫描 {openDetailBatch.scanned} · 重复 {openDetailBatch.duplicated} · 已有{' '}
              {openDetailBatch.skipped} · 入队 {openDetailBatch.queued}
            </Typography.Paragraph>
            {openDetailBatch.reason_message ? (
              <Alert type="error" message={openDetailBatch.reason_message} />
            ) : null}
            <Table<BatchItem>
              rowKey={(row) => `${row.doc_no}-${row.outcome}`}
              size="small"
              columns={itemColumns}
              dataSource={detail.items}
              pagination={false}
            />
          </>
        ) : null}
      </Drawer>
    </div>
  )
}
