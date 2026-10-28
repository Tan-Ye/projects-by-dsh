/**
 * WbEvidence · 执行产物展示
 *
 * 三类数据三种展示：
 *   doc    → 键值描述
 *   lines  → 表格
 *   其它   → 原始 JSON
 *
 * 可覆盖的类名：
 *   .wb-evidence              根元素
 *   .wb-evidence-raw          原始 JSON 块
 */

import { Descriptions, Table, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'

import './index.scss'

interface WbEvidenceProps {
  name: string
  payload: unknown
}

type RowData = Record<string, string>

function isRowArray(value: unknown): value is RowData[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'object' && item !== null)
}

function rowsToColumns(rows: RowData[]): ColumnsType<RowData> {
  const first = rows[0] ?? {}
  return Object.keys(first).map((key) => ({
    title: key,
    dataIndex: key,
    key,
    ellipsis: true,
  }))
}

export function WbEvidence({ name, payload }: WbEvidenceProps) {
  if (name === 'lines' && isRowArray(payload)) {
    return (
      <div className="wb-evidence">
        <Table<RowData>
          size="small"
          rowKey={(_, index) => String(index)}
          columns={rowsToColumns(payload)}
          dataSource={payload}
          pagination={false}
        />
      </div>
    )
  }

  if (name === 'doc' && payload !== null && typeof payload === 'object' && !Array.isArray(payload)) {
    const entries = Object.entries(payload as Record<string, string>)
    return (
      <div className="wb-evidence">
        <Descriptions size="small" column={2} bordered>
          {entries.map(([key, value]) => (
            <Descriptions.Item key={key} label={key}>
              {String(value)}
            </Descriptions.Item>
          ))}
        </Descriptions>
      </div>
    )
  }

  return (
    <div className="wb-evidence">
      <Typography.Paragraph className="wb-evidence-raw">
        <pre>{JSON.stringify(payload, null, 2)}</pre>
      </Typography.Paragraph>
    </div>
  )
}
