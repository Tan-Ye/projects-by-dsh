import assert from 'node:assert/strict'
import test from 'node:test'

import { formatDateTime, statusColor, statusText } from '../src/utils/format.ts'

test('四种状态都有中文文案', () => {
  assert.equal(statusText('draft'), '草稿')
  assert.equal(statusText('pending'), '待审批')
  assert.equal(statusText('submitted'), '已入账')
  assert.equal(statusText('voided'), '已作废')
})

test('未知状态原样返回，不能显示 undefined', () => {
  assert.equal(statusText('archived'), 'archived')
  assert.equal(statusText(''), '')
})

test('状态颜色与文案一一对应', () => {
  assert.equal(statusColor('draft'), 'default')
  assert.equal(statusColor('pending'), 'gold')
  assert.equal(statusColor('submitted'), 'green')
  assert.equal(statusColor('voided'), 'red')
  assert.equal(statusColor('unknown'), 'default')
})

test('时间只切到分钟，空值给破折号', () => {
  assert.equal(formatDateTime('2024-10-05 09:30:00'), '2024-10-05 09:30')
  assert.equal(formatDateTime(null), '—')
})
