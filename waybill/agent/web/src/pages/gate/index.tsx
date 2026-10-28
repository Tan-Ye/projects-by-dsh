/**
 * 人工闸门：等人工处理的任务。
 *
 * 两个动作：
 *   重跑       agent 再跑一次（可能上游数据修好了）
 *   标记处理   人已经在财务系统里手工补齐，留一条备注作为依据
 */

import {
  Alert,
  App,
  Button,
  Card,
  Empty,
  Input,
  Modal,
  Popconfirm,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { listGate, resolveTask, retryTask } from '@/services/gate'
import type { GateItem } from '@/services/gate/interface'
import { listGaps } from '@/services/gap'
import type { GapItem } from '@/services/gap/interface'

import styles from './index.module.scss'

export function GatePage() {
  const { message } = App.useApp()
  const [items, setItems] = useState<GateItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [gaps, setGaps] = useState<GapItem[]>([])

  const [resolving, setResolving] = useState<GateItem | null>(null)
  const [note, setNote] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listGate()
      setItems(data.items)
      setError('')
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
    // 科目缺口跟着闸门看：停在人工的单子，很多时候就是"科目表里没有这一项"
    listGaps()
      .then((data) => setGaps(data.items))
      .catch(() => setGaps([]))
  }, [refresh])

  async function onRetry(row: GateItem) {
    try {
      await retryTask(row.task_id)
      message.success('已重新入队，等 worker 执行')
      await refresh()
    } catch (exc) {
      message.error(exc instanceof Error ? exc.message : '重跑失败')
    }
  }

  async function onResolve() {
    if (!resolving) return
    setSubmitting(true)
    try {
      await resolveTask(resolving.task_id, note.trim())
      message.success('已标记处理')
      setResolving(null)
      setNote('')
      await refresh()
    } catch (exc) {
      message.error(exc instanceof Error ? exc.message : '操作失败')
    } finally {
      setSubmitting(false)
    }
  }

  const columns: ColumnsType<GateItem> = [
    {
      title: '单号',
      dataIndex: 'external_ref',
      key: 'external_ref',
      width: 160,
      render: (value: string | null) => value ?? <Typography.Text type="secondary">-</Typography.Text>,
    },
    { title: '任务', dataIndex: 'name', key: 'name', width: 200 },
    {
      title: '原因码',
      dataIndex: 'reason_code',
      key: 'reason_code',
      width: 200,
      render: (value: string | null) => (value ? <Tag color="orange">{value}</Tag> : '-'),
    },
    {
      title: '说明',
      dataIndex: 'reason_message',
      key: 'reason_message',
      ellipsis: true,
      render: (value: string | null) => value ?? '-',
    },
    {
      title: '重试次数',
      dataIndex: 'attempts',
      key: 'attempts',
      width: 100,
    },
    {
      title: '操作',
      key: 'actions',
      width: 220,
      render: (_: unknown, row: GateItem) => (
        <Space>
          <Popconfirm
            title="重跑这个任务？"
            description="会放回队列，由 worker 重新执行一次。"
            okText="重跑"
            cancelText="取消"
            onConfirm={() => onRetry(row)}
          >
            <Button size="small">重跑</Button>
          </Popconfirm>

          <Button size="small" type="primary" onClick={() => setResolving(row)}>
            标记处理
          </Button>

          {row.run_id ? (
            <Link to={`/runs/${row.run_id}`} className={styles.link}>
              看依据
            </Link>
          ) : null}
        </Space>
      ),
    },
  ]

  return (
    <div className={styles.page}>
      <Card size="small" className={styles.card}>
        <Typography.Paragraph type="secondary">
          agent 停下等人决策的任务。两种去向：数据修好后重跑；或者人已经处理完，留一条说明关掉。
        </Typography.Paragraph>

        {error ? <Alert type="error" message={error} /> : null}

        <Table<GateItem>
          rowKey="task_id"
          size="small"
          loading={loading}
          columns={columns}
          dataSource={items}
          pagination={false}
          locale={{ emptyText: <Empty description="没有待处理的任务" /> }}
        />
      </Card>

      <Card
        size="small"
        className={styles.card}
        title="科目缺口"
        extra={<Typography.Text type="secondary">按摘要聚合，agent 不改科目表</Typography.Text>}
      >
        <Typography.Paragraph type="secondary">
          下面是"没定下科目"的摘要。等 OA/财务那边新增科目后，agent 下次跑会自动读到，不需要改代码。
        </Typography.Paragraph>
        <Table<GapItem>
          rowKey="summary"
          size="small"
          columns={[
            { title: '摘要', dataIndex: 'summary', key: 'summary', ellipsis: true },
            { title: '出现次数', dataIndex: 'count', key: 'count', width: 100 },
            {
              title: '模型当时的说法',
              dataIndex: 'rationale',
              key: 'rationale',
              ellipsis: true,
              render: (value: string) => value || '-',
            },
            { title: '最近一次', dataIndex: 'last_at', key: 'last_at', width: 170 },
          ]}
          dataSource={gaps}
          pagination={false}
          locale={{ emptyText: <Empty description="没有科目缺口" /> }}
        />
      </Card>

      <Modal
        open={resolving !== null}
        title={`标记已处理：${resolving?.external_ref ?? resolving?.name ?? ''}`}
        okText="确认"
        cancelText="取消"
        confirmLoading={submitting}
        okButtonProps={{ disabled: note.trim().length === 0 }}
        onOk={onResolve}
        onCancel={() => {
          setResolving(null)
          setNote('')
        }}
      >
        <Typography.Paragraph type="secondary">
          说明会写进 gate_actions，谁处理的、依据是什么都要能查到。
        </Typography.Paragraph>
        <Input.TextArea
          rows={3}
          value={note}
          placeholder="例如：财务系统里手工补了成本中心，凭证 id=12"
          onChange={(event) => setNote(event.target.value)}
        />
      </Modal>
    </div>
  )
}
