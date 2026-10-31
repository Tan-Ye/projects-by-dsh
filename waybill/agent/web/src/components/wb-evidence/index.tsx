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

const SERIAL_COLUMN = '序号'

/**
 * 行 key：用明细自带的"序号"。
 *
 * 它是单据内的业务主键——同一张单里唯一，而且和位置无关，
 * 删一行、换一单都不会让身份错位。
 *
 * 兜底：目标系统的表如果没有序号列，只能拿整行内容当指纹，
 * 完全相同的两行再加后缀区分。下标永远不用——下标是位置，不是身份。
 */
function buildRowKeys(rows: RowData[]): Map<RowData, string> {
  const serials = rows.map((row) => (row[SERIAL_COLUMN] ?? '').trim())
  const serialsUsable =
    serials.every((value) => value !== '') && new Set(serials).size === serials.length

  const keys = new Map<RowData, string>()

  if (serialsUsable) {
    rows.forEach((row, position) => {
      keys.set(row, `${SERIAL_COLUMN}:${serials[position]}`)
    })
    return keys
  }

  const seen = new Map<string, number>()
  for (const row of rows) {
    const base = Object.entries(row)
      .map(([column, value]) => `${column}=${value}`)
      .join('|')
    const count = seen.get(base) ?? 0
    seen.set(base, count + 1)
    keys.set(row, count === 0 ? base : `${base}#${count}`)
  }
  return keys
}

export function WbEvidence({ name, payload }: WbEvidenceProps) {
  if (name === 'lines' && isRowArray(payload)) {
    const keys = buildRowKeys(payload)
    return (
      <div className="wb-evidence">
        <Table<RowData>
          size="small"
          rowKey={(row) => keys.get(row) ?? ''}
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
