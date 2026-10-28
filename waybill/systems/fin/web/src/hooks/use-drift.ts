/**
 * 漂移档位：同一份数据，不同的 DOM。
 *
 * 只改呈现，不改语义——三个档位下接口返回的数据完全一致。
 * 组件里只读 `config.xxx`，不许写 `if (version === 'v2')` 散落在各处。
 */

import type { AccountNode } from '@/services/meta/interface'

export type UiVersion = 'v1' | 'v2' | 'v3'

export interface UiConfig {
  version: UiVersion
  /** 保存按钮文案 */
  saveButtonText: string
  /** 成本中心控件：原生下拉 or 输入框 + 联想 */
  costCenterControl: 'select' | 'autocomplete'
  /** 金额输入是否带千分位 */
  amountMasked: boolean
  /** 新建时默认几行明细 */
  defaultLineCount: number
  /** 科目选项的标签顺序 */
  accountLabel: 'code-first' | 'name-first'
}

const STORAGE_KEY = 'fin_ui'

const CONFIG: Record<UiVersion, UiConfig> = {
  v1: {
    version: 'v1',
    saveButtonText: '保存',
    costCenterControl: 'select',
    amountMasked: false,
    defaultLineCount: 1,
    accountLabel: 'code-first',
  },
  v2: {
    version: 'v2',
    saveButtonText: '保存草稿',
    costCenterControl: 'autocomplete',
    amountMasked: false,
    defaultLineCount: 1,
    accountLabel: 'code-first',
  },
  v3: {
    version: 'v3',
    saveButtonText: '保存',
    costCenterControl: 'select',
    amountMasked: true,
    defaultLineCount: 2,
    accountLabel: 'name-first',
  },
}

function resolveVersion(): UiVersion {
  const asked = new URLSearchParams(window.location.search).get('ui')
  if (asked === 'v1' || asked === 'v2' || asked === 'v3') {
    localStorage.setItem(STORAGE_KEY, asked)
    return asked
  }
  const saved = localStorage.getItem(STORAGE_KEY)
  return saved === 'v2' || saved === 'v3' ? saved : 'v1'
}

// 整个会话只解析一次：刷新页面时档位不变，避免同一次操作中途切换
const CURRENT: UiConfig = CONFIG[resolveVersion()]

export function useDrift(): UiConfig {
  return CURRENT
}

/** 科目下拉的显示文案，v3 把名称放前面 */
export function formatAccountLabel(config: UiConfig, node: AccountNode): string {
  return config.accountLabel === 'code-first'
    ? `${node.code} ${node.name}`
    : `${node.name}（${node.code}）`
}
