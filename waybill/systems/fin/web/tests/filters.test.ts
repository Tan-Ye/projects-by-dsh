import assert from 'node:assert/strict'
import test from 'node:test'

import {
  defaultFilters,
  filtersKey,
  parseFilters,
  serializeFilters,
} from '../src/utils/filters.ts'

test('没存过时给默认值', () => {
  assert.deepEqual(parseFilters(null, ''), { status: '', external_ref: '', page: 1 })
  assert.deepEqual(parseFilters(null, 'pending'), {
    status: 'pending',
    external_ref: '',
    page: 1,
  })
})

test('存过就按存的来', () => {
  const raw = JSON.stringify({ status: 'draft', external_ref: 'BX-2024', page: 2 })
  assert.deepEqual(parseFilters(raw, 'pending'), {
    status: 'draft',
    external_ref: 'BX-2024',
    page: 2,
  })
})

test('坏掉的 JSON 退回默认值，不抛异常', () => {
  assert.deepEqual(parseFilters('{not json', 'pending'), defaultFilters('pending'))
  assert.deepEqual(parseFilters('null', 'pending'), defaultFilters('pending'))
})

test('字段类型不对时逐个纠正', () => {
  const raw = JSON.stringify({ status: 123, external_ref: null, page: '2' })
  assert.deepEqual(parseFilters(raw, 'draft'), {
    status: 'draft',        // 数字不是字符串 → 用默认状态
    external_ref: '',       // null 不是字符串 → 空
    page: 1,                // 字符串 "2" 不是整数 → 回第 1 页
  })
})

test('页码必须是不小于 1 的整数', () => {
  const cases: Array<[unknown, number]> = [
    [0, 1],
    [-3, 1],
    [1.5, 1],
    ['3', 1],
    [null, 1],
    [7, 7],
  ]
  for (const [page, expected] of cases) {
    const raw = JSON.stringify({ status: 'draft', external_ref: '', page })
    assert.equal(parseFilters(raw, 'draft').page, expected, `page=${String(page)}`)
  }
})

test('序列化后能原样解析回来', () => {
  const filters = { status: 'pending', external_ref: 'BX-1', page: 3 }
  assert.deepEqual(parseFilters(serializeFilters(filters), 'draft'), filters)
})

test('筛选条件按角色分开存', () => {
  assert.notEqual(filtersKey('maker'), filtersKey('checker'))
  assert.equal(filtersKey('maker'), 'fin_voucher_filters_maker')
  assert.equal(filtersKey(null), 'fin_voucher_filters_anonymous')
})
