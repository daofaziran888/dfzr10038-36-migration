import { request } from './client'

export type ReportReference = {
  id: number
  '报告id': number
  '报告编号': string
  '目录名称': string
  '来源定位': Record<string, string>
  '原始索引号': string | null
  '候选索引号列表': string[]
  '候选审计条目号列表': string[]
  '采用审计条目号': string | null
  '状态': string
  '签发来源类型': string | null
  '签发时间': string | null
  '待核项': string[]
  '更正id列表': number[]
  revision: number
}

export type AuditEntry = {
  id: number
  '记录编号'?: string
  '审计条目号'?: string
  '原始索引号'?: string
  '审计对象'?: string
  '审计类型'?: string
  '检查结果'?: string
  '审计时间'?: string
  '签发时间'?: string
  '签发人'?: string
  '整改状态'?: string
  status?: string
}

export type Correction = {
  id: number
  '更正编号': string
  '更正类型': string
  '证明力': string
  '原始索引号': string
  '审计条目号': string
  '签发时间': string | null
  '是否认可': boolean
  '状态': string
  '说明'?: string
  '提交时间': string
}

export type Disposition = {
  id: number
  '处置编号': string
  '报告id'?: number
  '报告编号'?: string
  '处置类型': string
  '采用审计条目号': string | null
  '原始索引号': string | null
  '采用证据类型': string
  '待核项': string[]
  '已认可更正': number[]
  '审计记录id': number | null
  '处置人': string
  '处置时间': string
  '说明': string
}

export type ReviewCase = {
  id: number
  '案件编号': string
  '状态': string
  '提交次数': number
  '处置id列表': number[]
}

export type ReportTraceDetail = {
  id: number
  '报告编号': string
  '报告类型': string
  '特征范围': string
  '报告原文'?: string
  '迁移触发来源'?: string | null
  '原始索引号'?: string | null
  '采用审计条目号'?: string | null
  '报告引用': ReportReference | null
  '候选目录': { '索引编号': string; '目录名称': string; '父目录': string; '状态': string; '创建时间': string }[]
  '审计条目': AuditEntry[]
  '审计更正': Correction[]
  '复查案件': ReviewCase | null
  '审计处置': Disposition[]
  status: string
}

export type AuditTraceDetail = AuditEntry & {
  '报告引用': ReportReference[]
  '审计处置': Disposition[]
}

export type TraceResult = {
  ok: boolean
  message: string
  reference?: ReportReference
  case?: ReviewCase
  disposition?: Disposition
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await request(path, { method: 'POST', body: JSON.stringify(body) })
  return (await response.json()) as T
}

export async function loadReportTrace(reportId: number): Promise<ReportTraceDetail> {
  const response = await request(`/api/trace/reports/${reportId}`)
  if (!response.ok) throw new Error('报告引用读取失败')
  return (await response.json()) as ReportTraceDetail
}

export async function loadAuditTrace(auditId: number): Promise<AuditTraceDetail> {
  const response = await request(`/api/trace/audits/${auditId}`)
  if (!response.ok) throw new Error('审计引用读取失败')
  return (await response.json()) as AuditTraceDetail
}

export async function migrateReports(reportIds: number[] = []): Promise<TraceResult & { migrated?: unknown[] }> {
  return await postJson('/api/trace/migrate', { report_ids: reportIds })
}

export async function submitCorrection(
  reportId: number,
  values: Record<string, string>,
): Promise<TraceResult> {
  return await postJson(`/api/trace/reports/${reportId}/corrections`, { values })
}

export async function submitReview(
  reportId: number,
  action: string,
  evidenceType: string,
  remark: string,
): Promise<TraceResult> {
  return await postJson(`/api/trace/reports/${reportId}/review`, {
    action,
    evidence_type: evidenceType,
    remark,
  })
}

export async function openAuditDisposition(
  auditId: number,
  reportId: number | null,
  evidenceType: string,
  remark: string,
): Promise<TraceResult> {
  return await postJson(`/api/trace/audits/${auditId}/dispositions`, {
    report_id: reportId,
    evidence_type: evidenceType,
    remark,
  })
}
