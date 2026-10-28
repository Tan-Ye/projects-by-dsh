/**
 * 评测：五个固定用例、四个指标。
 *
 * 页面只做两件事：看某一次的结果、对比任意两次。
 * 对比是这个页面存在的理由——"改完之后有没有变差"。
 */

import { Alert, Button, Card, Descriptions, Drawer, Empty, Modal, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { getEval, listEvals } from '@/services/eval'
import type { EvalCase, EvalDetail, EvalSummary } from '@/services/eval/interface'

import styles from './index.module.scss'

const METRIC_KEYS = ['执行成功率', '拦截准确率', '误拦率', '误放率']

export function EvalPage() {
  const [items, setItems] = useState<EvalSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [selected, setSelected] = useState<number[]>([])
  const [detail, setDetail] = useState<EvalDetail | null>(null)
  const [compare, setCompare] = useState<[EvalSummary, EvalSummary] | null>(null)

  const refresh = useCallback(async () => {
    try {
      const data = await listEvals()
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
  }, [refresh])

  async function openDetail(id: number) {
    setDetail(await getEval(id))
  }

  function openCompare() {
    const picked = items.filter((item) => selected.includes(item.id))
    if (picked.length === 2) {
      setCompare([picked[1], picked[0]])
    }
  }

  const columns: ColumnsType<EvalSummary> = [
    { title: '标签', dataIndex: 'label', key: 'label', width: 160 },
    {
      title: '通过',
      key: 'passed',
      width: 110,
      render: (_: unknown, row: EvalSummary) => (
        <Tag color={row.passed === row.total ? 'success' : 'warning'}>
          {row.passed} / {row.total}
        </Tag>
      ),
    },
    ...METRIC_KEYS.map((key) => ({
      title: key,
      key,
      width: 110,
      render: (_: unknown, row: EvalSummary) => `${row.metrics[key] ?? 0}%`,
    })),
    { title: '执行人', dataIndex: 'created_by', key: 'created_by', width: 100 },
    { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 180 },
    {
      title: '操作',
      key: 'actions',
      width: 90,
      render: (_: unknown, row: EvalSummary) => (
        <Button size="small" onClick={() => void openDetail(row.id)}>
          明细
        </Button>
      ),
    },
  ]

  const caseColumns: ColumnsType<EvalCase> = [
    { title: '用例', dataIndex: 'id', key: 'id', width: 80 },
    { title: '名称', dataIndex: 'name', key: 'name', ellipsis: true },
    { title: '终态', dataIndex: 'status', key: 'status', width: 140 },
    {
      title: '原因码',
      dataIndex: 'reason_code',
      key: 'reason_code',
      width: 180,
      render: (value: string | null) => (value ? <Tag color="orange">{value}</Tag> : '-'),
    },
    {
      title: '结果',
      dataIndex: 'passed',
      key: 'passed',
      width: 90,
      render: (value: boolean) =>
        value ? <Tag color="success">通过</Tag> : <Tag color="error">失败</Tag>,
    },
    {
      title: '说明',
      dataIndex: 'problems',
      key: 'problems',
      ellipsis: true,
      render: (value: string[]) => (value.length ? value.join('；') : '-'),
    },
  ]

  const compareRows = useMemo(() => {
    if (!compare) return []
    const [before, after] = compare
    return METRIC_KEYS.map((key) => {
      const from = before.metrics[key] ?? 0
      const to = after.metrics[key] ?? 0
      const delta = Number((to - from).toFixed(1))
      return { key, from, to, delta }
    })
  }, [compare])

  return (
    <div className={styles.page}>
      <Card size="small" className={styles.card}>
        <div className={styles.toolbar}>
          <Typography.Text type="secondary">
            五个固定用例：两个必须成功、三个必须主动停下。判定看财务系统终态，不看 agent 自述。
          </Typography.Text>
          <Button disabled={selected.length !== 2} onClick={openCompare}>
            对比选中的两次（{selected.length}/2）
          </Button>
        </div>

        {error ? <Alert type="error" message={error} /> : null}

        <Table<EvalSummary>
          rowKey="id"
          size="small"
          loading={loading}
          columns={columns}
          dataSource={items}
          pagination={{ pageSize: 10, showSizeChanger: false }}
          rowSelection={{
            selectedRowKeys: selected,
            onChange: (keys) => setSelected(keys.map(Number).slice(-2)),
            getCheckboxProps: () => ({ disabled: false }),
          }}
          locale={{ emptyText: <Empty description="还没有评测结果，跑一次 python -m scripts.evaluate" /> }}
        />
      </Card>

      <Drawer
        open={detail !== null}
        width={860}
        title={`评测 ${detail?.label ?? ''}`}
        onClose={() => setDetail(null)}
      >
        {detail ? (
          <>
            <Descriptions size="small" column={4} className={styles.metrics}>
              {METRIC_KEYS.map((key) => (
                <Descriptions.Item key={key} label={key}>
                  {detail.metrics[key] ?? 0}%
                </Descriptions.Item>
              ))}
            </Descriptions>
            <Table<EvalCase>
              rowKey="id"
              size="small"
              columns={caseColumns}
              dataSource={detail.cases}
              pagination={false}
            />
          </>
        ) : null}
      </Drawer>

      <Modal
        open={compare !== null}
        title="两次评测对比"
        footer={null}
        width={560}
        onCancel={() => setCompare(null)}
      >
        {compare ? (
          <>
            <Typography.Paragraph type="secondary">
              从「{compare[0].label}」到「{compare[1].label}」
            </Typography.Paragraph>
            <Table
              rowKey="key"
              size="small"
              pagination={false}
              columns={[
                { title: '指标', dataIndex: 'key', key: 'key' },
                { title: '之前', dataIndex: 'from', key: 'from', render: (v: number) => `${v}%` },
                { title: '之后', dataIndex: 'to', key: 'to', render: (v: number) => `${v}%` },
                {
                  title: '变化',
                  dataIndex: 'delta',
                  key: 'delta',
                  render: (v: number) => (
                    <Tag color={v > 0 ? 'error' : v < 0 ? 'success' : 'default'}>
                      {v > 0 ? '+' : ''}
                      {v}
                    </Tag>
                  ),
                },
              ]}
              dataSource={compareRows}
            />
          </>
        ) : null}
      </Modal>
    </div>
  )
}
