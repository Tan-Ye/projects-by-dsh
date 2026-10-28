/**
 * 运行详情：三层下钻。
 *
 *   L1 结论  这张单处于什么状态、为什么
 *   L2 过程  十来个步骤各自做了什么、成没成
 *   L3 证据  读到的原文、模型判断、字段核验、自愈记录
 */

import { Alert, Card, Descriptions, Empty, Spin, Table, Tabs, Tag, Timeline, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'

import { WbEvidence } from '@/components/wb-evidence'
import { WbStatusTag } from '@/components/wb-status-tag'
import { getRun } from '@/services/run'
import type {
  JudgmentItem,
  RepairItem,
  RunDetail,
  VerificationItem,
} from '@/services/run/interface'
import type { StepItem } from '@/types'

import styles from './index.module.scss'

function totalMs(steps: StepItem[]): number {
  return steps.reduce((sum, step) => sum + step.duration_ms, 0)
}

export function RunDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [detail, setDetail] = useState<RunDetail | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!id) return
    getRun(Number(id))
      .then(setDetail)
      .catch((exc: unknown) => setError(exc instanceof Error ? exc.message : '加载失败'))
  }, [id])

  if (error) return <Alert type="error" message={error} />
  if (!detail) {
    return (
      <div className={styles.loading}>
        <Spin />
      </div>
    )
  }

  const { run, steps, extractions, verifications, judgments, repairs } = detail

  const stepColumns: ColumnsType<StepItem> = [
    { title: '#', dataIndex: 'seq', key: 'seq', width: 56 },
    { title: '意图', dataIndex: 'intent', key: 'intent' },
    { title: '动作', dataIndex: 'action', key: 'action', width: 150 },
    { title: '耗时', dataIndex: 'duration_ms', key: 'duration_ms', width: 90, render: (ms: number) => `${ms} ms` },
    {
      title: '失败位置',
      dataIndex: 'target_path',
      key: 'target_path',
      width: 160,
      render: (value: string | null) => value ?? '-',
    },
  ]

  const verificationColumns: ColumnsType<VerificationItem> = [
    { title: '层', dataIndex: 'layer', key: 'layer', width: 120 },
    { title: '字段', dataIndex: 'field', key: 'field', width: 160 },
    {
      title: '结果',
      dataIndex: 'passed',
      key: 'passed',
      width: 90,
      render: (passed: number) => (passed ? <Tag color="success">一致</Tag> : <Tag color="error">不一致</Tag>),
    },
    { title: '期望', dataIndex: 'expected', key: 'expected' },
    { title: '实际', dataIndex: 'actual', key: 'actual' },
    {
      title: '原因码',
      dataIndex: 'reason_code',
      key: 'reason_code',
      width: 180,
      render: (value: string | null) => value ?? '-',
    },
  ]

  const judgmentColumns: ColumnsType<JudgmentItem> = [
    { title: '摘要', dataIndex: 'summary', key: 'summary', ellipsis: true },
    { title: '选中', dataIndex: 'chosen', key: 'chosen', width: 120, render: (value: string | null) => value ?? '-' },
    {
      title: '置信度',
      dataIndex: 'confidence',
      key: 'confidence',
      width: 100,
      render: (value: number | null) => (value === null ? '-' : value.toFixed(2)),
    },
    {
      title: '采信',
      dataIndex: 'accepted',
      key: 'accepted',
      width: 90,
      render: (accepted: number) => (accepted ? <Tag color="success">采信</Tag> : <Tag>未采信</Tag>),
    },
    { title: '理由', dataIndex: 'rationale', key: 'rationale', ellipsis: true },
  ]

  const repairColumns: ColumnsType<RepairItem> = [
    { title: '步骤', dataIndex: 'step_seq', key: 'step_seq', width: 80 },
    {
      title: '结果',
      dataIndex: 'outcome',
      key: 'outcome',
      width: 120,
      render: (value: RepairItem['outcome']) =>
        value === 'retried_ok' ? <Tag color="success">已修好</Tag> : <Tag color="error">未修好</Tag>,
    },
    {
      title: '旧定位',
      dataIndex: 'old_target',
      key: 'old_target',
      render: (value: unknown) => <Typography.Text code>{JSON.stringify(value)}</Typography.Text>,
    },
    {
      title: '新定位',
      dataIndex: 'new_target',
      key: 'new_target',
      render: (value: unknown) => <Typography.Text code>{JSON.stringify(value)}</Typography.Text>,
    },
    {
      title: '置信度',
      dataIndex: 'confidence',
      key: 'confidence',
      width: 100,
      render: (value: number | null) => (value === null ? '-' : value.toFixed(2)),
    },
    { title: '理由', dataIndex: 'rationale', key: 'rationale', ellipsis: true },
  ]

  return (
    <div className={styles.page}>
      <Card className={styles.summary}>
        <div className={styles.summaryHead}>
          <Typography.Title level={4} className={styles.title}>
            {run.external_ref ?? run.task_name}
          </Typography.Title>
          <WbStatusTag status={run.status} />
          {run.reason_code ? <Tag color="orange">{run.reason_code}</Tag> : null}
        </div>

        <Typography.Paragraph type="secondary" className={styles.message}>
          {run.reason_message ?? '无异常'}
        </Typography.Paragraph>

        <Descriptions size="small" column={4}>
          <Descriptions.Item label="配方">
            {run.recipe_name} v{run.recipe_version}
          </Descriptions.Item>
          <Descriptions.Item label="开始时间">{run.started_at}</Descriptions.Item>
          <Descriptions.Item label="结束时间">{run.finished_at ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="步骤耗时">{totalMs(steps)} ms</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="执行过程" size="small">
        <Timeline
          items={steps.map((step) => ({
            color: step.outcome === 'ok' ? 'green' : 'red',
            children: (
              <div className={styles.stepRow}>
                <span className={styles.stepSeq}>{step.seq}</span>
                <span className={styles.stepIntent}>{step.intent}</span>
                <Typography.Text code>{step.action}</Typography.Text>
                <Typography.Text type="secondary">{step.duration_ms} ms</Typography.Text>
                {step.reason_code ? <Tag color="red">{step.reason_code}</Tag> : null}
                {step.target_path ? (
                  <Typography.Text type="secondary">{step.target_path}</Typography.Text>
                ) : null}
              </div>
            ),
          }))}
        />
      </Card>

      <Card title="证据与核验" size="small">
        <Tabs
          items={[
            {
              key: 'evidence',
              label: `执行产物（${extractions.length}）`,
              children: extractions.length ? (
                <div className={styles.stack}>
                  {extractions.map((item) => (
                    <div key={item.name}>
                      <Typography.Text strong>{item.name}</Typography.Text>
                      <Typography.Text type="secondary" className={styles.hash}>
                        sha256 {item.sha256.slice(0, 12)}
                      </Typography.Text>
                      <WbEvidence name={item.name} payload={item.payload} />
                    </div>
                  ))}
                </div>
              ) : (
                <Empty description="没有产物" />
              ),
            },
            {
              key: 'verify',
              label: `字段核验（${verifications.length}）`,
              children: verifications.length ? (
                <Table<VerificationItem>
                  size="small"
                  rowKey={(row) => `${row.layer}-${row.field}`}
                  columns={verificationColumns}
                  dataSource={verifications}
                  pagination={false}
                />
              ) : (
                <Empty description="未走到核验" />
              ),
            },
            {
              key: 'judgment',
              label: `模型判断（${judgments.length}）`,
              children: judgments.length ? (
                <Table<JudgmentItem>
                  size="small"
                  rowKey={(row) => row.summary}
                  columns={judgmentColumns}
                  dataSource={judgments}
                  pagination={false}
                />
              ) : (
                <Empty description="这次没调模型" />
              ),
            },
            {
              key: 'repair',
              label: `自愈（${repairs.length}）`,
              children: repairs.length ? (
                <Table<RepairItem>
                  size="small"
                  rowKey={(row) => `${row.step_seq}-${row.outcome}`}
                  columns={repairColumns}
                  dataSource={repairs}
                  pagination={false}
                />
              ) : (
                <Empty description="没有触发自愈" />
              ),
            },
          ]}
        />
      </Card>

      <Card title="步骤明细" size="small">
        <Table<StepItem>
          size="small"
          rowKey="seq"
          columns={stepColumns}
          dataSource={steps}
          pagination={false}
        />
      </Card>
    </div>
  )
}
