/**
 * 凭证新建 / 编辑页。
 *
 * 新建走 `/vouchers/new`，编辑走 `/vouchers/:id`，同一个表单。
 * 保存 = 整张单据覆盖：服务端会跑一遍校验，失败也是 200，错误在 body 里。
 */

import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Alert, App, AutoComplete, DatePicker, Input, Modal, Select, Space, Tag, Typography } from 'antd'
import dayjs from 'dayjs'

import { FinButton } from '@/components/fin-button'
import { formatAccountLabel, useDrift, useMeta } from '@/hooks'
import { currentRole } from '@/services/auth'
import { ApiError } from '@/services/http'
import { getCostCenters } from '@/services/meta'
import type { AccountNode, CostCenter } from '@/services/meta/interface'
import {
  approveVoucher,
  createVoucher,
  getVoucher,
  rejectVoucher,
  saveVoucher,
  submitVoucher,
} from '@/services/voucher'
import type { VoucherInput } from '@/services/voucher/interface'
import type { FieldError } from '@/types'
import { centsToYuan, statusColor, statusText, yuanToCents } from '@/utils'

import styles from './voucher-edit.module.scss'

interface LineState {
  key: number
  account_code: string
  cost_center: string
  amount: string
  summary: string
}

let nextKey = 1

function blankLine(costCenter = ''): LineState {
  return { key: nextKey++, account_code: '', cost_center: costCenter, amount: '', summary: '' }
}

/** 科目树展平成可选项，只要末级 */
function flattenLeaves(nodes: AccountNode[]): AccountNode[] {
  return nodes.flatMap((node) => (node.is_leaf ? [node] : flattenLeaves(node.children)))
}

export function VoucherEditPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { message } = App.useApp()
  const config = useDrift()
  const { accounts, departments, error: metaError } = useMeta()

  const voucherId = id ? Number(id) : null
  const isNew = voucherId === null

  const [externalRef, setExternalRef] = useState('')
  const [voucherDate, setVoucherDate] = useState(dayjs().format('YYYY-MM-DD'))
  const [summary, setSummary] = useState('')
  const [deptCode, setDeptCode] = useState('')
  const [attachmentCount, setAttachmentCount] = useState(1)
  const [lines, setLines] = useState<LineState[]>([blankLine()])

  const [costCenters, setCostCenters] = useState<CostCenter[]>([])
  const [status, setStatus] = useState('draft')
  const [voucherNo, setVoucherNo] = useState<string | null>(null)
  const [reviewNote, setReviewNote] = useState<string | null>(null)
  const [serverErrors, setServerErrors] = useState<FieldError[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [reviewing, setReviewing] = useState(false)
  const [rejectOpen, setRejectOpen] = useState(false)
  const [rejectNote, setRejectNote] = useState('')

  // 制单人才改得动草稿；复核人一律只读，只做通过/驳回
  const role = currentRole()
  const editable = role === 'maker' && status === 'draft'

  const loadCostCenters = useCallback(async (dept: string) => {
    if (!dept) {
      setCostCenters([])
      return
    }
    try {
      setCostCenters(await getCostCenters(dept))
    } catch (err) {
      setCostCenters([])
      if (err instanceof ApiError) message.error(err.message)
    }
  }, [message])

  // 编辑态：载入已有凭证
  useEffect(() => {
    if (isNew) return
    let cancelled = false

    async function load() {
      try {
        const detail = await getVoucher(voucherId as number)
        if (cancelled) return
        setExternalRef(detail.external_ref)
        setVoucherDate(detail.voucher_date)
        setSummary(detail.summary)
        setDeptCode(detail.dept_code)
        setAttachmentCount(detail.attachment_count)
        setStatus(detail.status)
        setVoucherNo(detail.voucher_no)
        setReviewNote(detail.review_note)
        setServerErrors(detail.errors)
        setLines(
          detail.lines.length
            ? detail.lines.map((line) => ({
                key: nextKey++,
                account_code: line.account_code,
                cost_center: line.cost_center,
                amount: centsToYuan(line.debit_cents),
                summary: line.summary,
              }))
            : [blankLine()],
        )
        void loadCostCenters(detail.dept_code)
      } catch (err) {
        if (!cancelled) setLoadError(err instanceof ApiError ? err.message : '凭证加载失败')
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [isNew, voucherId, loadCostCenters])

  // 新建态：按漂移档位决定默认行数
  useEffect(() => {
    if (isNew) setLines(Array.from({ length: config.defaultLineCount }, () => blankLine()))
  }, [isNew, config.defaultLineCount])

  function updateLine(key: number, patch: Partial<LineState>) {
    setLines((prev) => prev.map((line) => (line.key === key ? { ...line, ...patch } : line)))
  }

  async function handleDeptChange(next: string) {
    setDeptCode(next)
    // 部门一变，原有成本中心几乎一定不属于新部门，直接清掉
    setLines((prev) => prev.map((line) => ({ ...line, cost_center: '' })))
    await loadCostCenters(next)
  }

  function buildPayload(): VoucherInput | null {
    for (const line of lines) {
      if (Number.isNaN(yuanToCents(line.amount))) {
        setServerErrors([{ field: 'lines', code: 'AMOUNT_INVALID', message: '金额格式不正确' }])
        return null
      }
    }
    return {
      external_ref: externalRef.trim(),
      voucher_date: voucherDate,
      summary,
      dept_code: deptCode,
      attachment_count: attachmentCount,
      lines: lines.map((line) => ({
        account_code: line.account_code,
        cost_center: line.cost_center,
        debit_cents: yuanToCents(line.amount) || 0,
        summary: line.summary,
      })),
    }
  }

  async function handleSave() {
    const payload = buildPayload()
    if (!payload) return

    setSaving(true)
    setServerErrors([])
    try {
      if (isNew) {
        const result = await createVoucher(payload)
        if (result.ok) {
          message.success('已保存')
        } else {
          // 建单成功但校验没过，服务端已经落库——切到编辑态继续改
          message.warning('单据已创建，但有校验未通过')
        }
        navigate(`/vouchers/${result.id}`, { replace: true })
      } else {
        const result = await saveVoucher(voucherId as number, payload)
        setServerErrors(result.errors)
        if (result.ok) message.success('已保存')
        else message.warning('保存成功，但有校验未通过')
      }
    } catch (err) {
      message.error(err instanceof ApiError ? err.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  async function handleSubmit() {
    setReviewing(true)
    try {
      const detail = await submitVoucher(voucherId as number)
      setStatus(detail.status)
      setReviewNote(detail.review_note)
      message.success('已提交审批，等待复核人处理')
    } catch (err) {
      message.error(err instanceof ApiError ? err.message : '提交失败')
    } finally {
      setReviewing(false)
    }
  }

  async function handleApprove() {
    setReviewing(true)
    try {
      const detail = await approveVoucher(voucherId as number)
      setStatus(detail.status)
      setVoucherNo(detail.voucher_no)
      message.success('复核通过，凭证已入账')
    } catch (err) {
      message.error(err instanceof ApiError ? err.message : '复核失败')
    } finally {
      setReviewing(false)
    }
  }

  async function handleReject() {
    setReviewing(true)
    try {
      const detail = await rejectVoucher(voucherId as number, rejectNote)
      setStatus(detail.status)
      setReviewNote(detail.review_note)
      setRejectOpen(false)
      setRejectNote('')
      message.success('已驳回，制单人可以修改后重新提交')
    } catch (err) {
      message.error(err instanceof ApiError ? err.message : '驳回失败')
    } finally {
      setReviewing(false)
    }
  }

  function errorOf(field: string): string | null {
    return serverErrors.find((item) => item.field === field)?.message ?? null
  }

  const accountOptions = flattenLeaves(accounts).map((node) => ({
    value: node.code,
    label: formatAccountLabel(config, node),
  }))

  const costCenterOptions = costCenters.map((center) => ({
    value: center.code,
    label: center.is_default ? `${center.name}（默认）` : center.name,
  }))

  if (loadError) {
    return (
      <div className={styles.page}>
        <Alert type="error" message={loadError} showIcon />
      </div>
    )
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <Space align="center">
          <Typography.Title level={4} className={styles.title}>
            {isNew ? '新建凭证' : `凭证 #${voucherId}`}
          </Typography.Title>
          {!isNew && <Tag color={statusColor(status)}>{statusText(status)}</Tag>}
          {voucherNo && <span className={styles.voucherNo}>{voucherNo}</span>}
        </Space>

        <Space>
          <FinButton onClick={() => navigate('/vouchers')}>返回列表</FinButton>
          {editable && (
            <FinButton
              type="primary"
              loading={saving}
              loadingText="保存中…"
              onClick={() => void handleSave()}
            >
              {config.saveButtonText}
            </FinButton>
          )}
          {!isNew && editable && (
            <FinButton
              loading={reviewing}
              loadingText="提交中…"
              onClick={() => void handleSubmit()}
            >
              提交审批
            </FinButton>
          )}
          {!isNew && status === 'pending' && role === 'checker' && (
            <>
              <FinButton
                type="primary"
                loading={reviewing}
                loadingText="处理中…"
                onClick={() => void handleApprove()}
              >
                通过入账
              </FinButton>
              <FinButton danger onClick={() => setRejectOpen(true)}>
                驳回
              </FinButton>
            </>
          )}
        </Space>
      </div>

      {metaError && <Alert type="error" message={metaError} showIcon className={styles.alert} />}

      {status === 'pending' && (
        <Alert
          type="info"
          showIcon
          className={styles.alert}
          message={
            role === 'checker'
              ? '这张凭证等你复核：通过后入账并分配凭证号，驳回则退回制单人。'
              : '已提交审批，等待复核人处理。这期间不能修改。'
          }
        />
      )}

      {status === 'submitted' && (
        <Alert
          type="success"
          showIcon
          className={styles.alert}
          message={`已入账${voucherNo ? `，凭证号 ${voucherNo}` : ''}`}
        />
      )}

      {status === 'draft' && reviewNote && (
        <Alert
          type="error"
          showIcon
          className={styles.alert}
          message="上一次复核被驳回"
          description={reviewNote}
        />
      )}

      {status === 'draft' && (
        <Alert
          type="info"
          showIcon
          className={styles.alert}
          message={
            role === 'maker'
              ? isNew
                ? '填完整张单据后保存，保存会触发服务端校验。'
                : '草稿状态：保存后点「提交审批」，由复核人通过后才算入账。'
              : '这张凭证是草稿，只有制单人能修改。等它提交后你才能复核。'
          }
        />
      )}

      {serverErrors.length > 0 && (
        <Alert
          type="warning"
          showIcon
          className={styles.alert}
          message={`有 ${serverErrors.length} 项校验未通过`}
          description={
            <ul className={styles.errorList}>
              {serverErrors.map((item) => (
                <li key={`${item.field}-${item.code}`}>
                  {item.field}：{item.message}
                </li>
              ))}
            </ul>
          }
        />
      )}

      <div className={styles.card}>
        <div className={styles.grid}>
          <label className={styles.field}>
            外部单号
            <Input
              value={externalRef}
              disabled={!isNew}
              onChange={(event) => setExternalRef(event.target.value)}
              placeholder="如 BX-2024-0912"
            />
            {errorOf('external_ref') && <span className={styles.error}>{errorOf('external_ref')}</span>}
          </label>

          <label className={styles.field}>
            凭证日期
            <DatePicker
              value={dayjs(voucherDate)}
              allowClear={false}
              disabled={!editable}
              onChange={(value) => value && setVoucherDate(value.format('YYYY-MM-DD'))}
              style={{ width: '100%' }}
            />
          </label>

          <label className={styles.field}>
            部门
            <Select
              value={deptCode || undefined}
              disabled={!editable}
              placeholder="选择部门"
              onChange={(value) => void handleDeptChange(value)}
              options={departments.map((dept) => ({ value: dept.code, label: dept.name }))}
            />
            {errorOf('dept_code') && <span className={styles.error}>{errorOf('dept_code')}</span>}
          </label>

          <label className={styles.field}>
            附单据数
            <Input
              value={String(attachmentCount)}
              disabled={!editable}
              onChange={(event) => setAttachmentCount(Number(event.target.value) || 0)}
              inputMode="numeric"
            />
            {errorOf('attachment_count') && (
              <span className={styles.error}>{errorOf('attachment_count')}</span>
            )}
          </label>

          <label className={`${styles.field} ${styles.wide}`}>
            摘要
            <Input
              value={summary}
              disabled={!editable}
              onChange={(event) => setSummary(event.target.value)}
              placeholder="报销事由"
            />
            {errorOf('summary') && <span className={styles.error}>{errorOf('summary')}</span>}
          </label>
        </div>

        <div className={styles.lines}>
          <div className={styles.linesHeader}>
            <span>明细</span>
            {editable && (
              <FinButton size="small" onClick={() => setLines((prev) => [...prev, blankLine()])}>
                加一行
              </FinButton>
            )}
          </div>

          {lines.map((line, index) => {
            const lineError = errorOf(`lines[${index}].account_code`)
            const amountError = errorOf(`lines[${index}].debit_cents`)

            return (
              <div className={styles.lineRow} key={line.key}>
                <Select
                  className={styles.lineAccount}
                  value={line.account_code || undefined}
                  disabled={!editable}
                  placeholder="科目"
                  showSearch
                  optionFilterProp="label"
                  onChange={(value) => updateLine(line.key, { account_code: value })}
                  options={accountOptions}
                />

                {config.costCenterControl === 'autocomplete' ? (
                  <AutoComplete
                    className={styles.lineCenter}
                    value={line.cost_center}
                    disabled={!editable}
                    placeholder="成本中心"
                    onChange={(value) => updateLine(line.key, { cost_center: value })}
                    options={costCenterOptions}
                  />
                ) : (
                  <Select
                    className={styles.lineCenter}
                    value={line.cost_center || undefined}
                    disabled={!editable}
                    placeholder="成本中心"
                    onChange={(value) => updateLine(line.key, { cost_center: value })}
                    options={costCenterOptions}
                  />
                )}

                <Input
                  className={styles.lineAmount}
                  value={line.amount}
                  disabled={!editable}
                  placeholder="金额（元）"
                  inputMode="decimal"
                  onChange={(event) => updateLine(line.key, { amount: event.target.value })}
                />

                <Input
                  className={styles.lineSummary}
                  value={line.summary}
                  disabled={!editable}
                  placeholder="备注"
                  onChange={(event) => updateLine(line.key, { summary: event.target.value })}
                />

                {editable && (
                  <FinButton
                    size="small"
                    onClick={() => setLines((prev) => prev.filter((item) => item.key !== line.key))}
                  >
                    删除
                  </FinButton>
                )}

                {lineError && <span className={styles.error}>{lineError}</span>}
                {amountError && <span className={styles.error}>{amountError}</span>}
              </div>
            )
          })}
        </div>
      </div>

      <Modal
        title="驳回凭证"
        open={rejectOpen}
        confirmLoading={reviewing}
        okText="确认驳回"
        cancelText="取消"
        onOk={() => void handleReject()}
        onCancel={() => setRejectOpen(false)}
      >
        <Input.TextArea
          rows={3}
          value={rejectNote}
          onChange={(event) => setRejectNote(event.target.value)}
          placeholder="写清为什么不通过，制单人据此修改"
        />
      </Modal>
    </div>
  )
}
