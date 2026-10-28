import assert from 'node:assert/strict'
import test from 'node:test'

import { centsToYuan, centsToYuanGrouped, yuanToCents } from '../src/utils/money.ts'

test('yuanToCents：整数和小数都能精确转成分', () => {
  assert.equal(yuanToCents('128.60'), 12860)
  assert.equal(yuanToCents('128.6'), 12860)
  assert.equal(yuanToCents('128'), 12800)
  assert.equal(yuanToCents('0.07'), 7)
  assert.equal(yuanToCents('0.1'), 10)
  assert.equal(yuanToCents('0'), 0)
})

test('yuanToCents：浮点乘法会出错的用例', () => {
  // 0.29 * 100 === 28.999999999999996
  assert.equal(yuanToCents('0.29'), 29)
  // 1.15 * 100 === 114.99999999999999
  assert.equal(yuanToCents('1.15'), 115)
  assert.equal(yuanToCents('9999999.99'), 999999999)
})

test('yuanToCents：前后空格不影响结果', () => {
  assert.equal(yuanToCents('  128.60  '), 12860)
})

test('yuanToCents：非法输入返回 NaN', () => {
  assert.ok(Number.isNaN(yuanToCents('')))
  assert.ok(Number.isNaN(yuanToCents('abc')))
  assert.ok(Number.isNaN(yuanToCents('-1')))
  assert.ok(Number.isNaN(yuanToCents('1.005')))
  assert.ok(Number.isNaN(yuanToCents('1,280.00')))
  assert.ok(Number.isNaN(yuanToCents('.5')))
  assert.ok(Number.isNaN(yuanToCents('1.')))
})

test('centsToYuan：始终两位小数', () => {
  assert.equal(centsToYuan(12860), '128.60')
  assert.equal(centsToYuan(0), '0.00')
  assert.equal(centsToYuan(5), '0.05')
  assert.equal(centsToYuan(999999999), '9999999.99')
})

test('centsToYuanGrouped：千分位只在展示时加', () => {
  assert.equal(centsToYuanGrouped(12860), '128.60')
  assert.equal(centsToYuanGrouped(128600), '1,286.00')
  assert.equal(centsToYuanGrouped(123456789), '1,234,567.89')
})

test('往返转换不丢精度', () => {
  for (const value of [0, 1, 7, 99, 100, 12345, 999999999]) {
    const text = centsToYuan(value)
    assert.equal(yuanToCents(text), value, `${value} 往返后变了`)
  }
})
