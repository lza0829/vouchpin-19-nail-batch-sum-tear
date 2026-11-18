// 钉后互证展示文案（前后端共用口径）
export const STRATEGY_LABELS = {
  events: '以事件湖重算为准',
  batch: '以批头+明细为准',
}

export const BATCH_STATUS = {
  sealed: { label: '已钉', cls: 'ok' },
  disputed: { label: '争议', cls: 'bad' },
  voided: { label: '已解钉', cls: 'muted' },
}

export const RECON_STATE = {
  ok: { label: '一致', cls: 'ok' },
  diverged: { label: '有差异', cls: 'bad' },
}

export const BUCKET_LABELS = {
  count: '笔数',
  amount: '金额',
  missing_event: '缺事件',
  missing_fact: '缺事实',
}

export function batchStatus(s) {
  return BATCH_STATUS[s] || { label: s, cls: '' }
}

export function reconState(s) {
  return RECON_STATE[s] || { label: s || '未知', cls: '' }
}
