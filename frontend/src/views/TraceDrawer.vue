<template>
  <div v-if="detail" class="trace-panel" :data-report-id="detail.id">
    <div class="trace-head">
      <div>
        <h3>可追证报告引用 · {{ detail['报告编号'] }}</h3>
        <p class="trace-sub">
          {{ detail['特征范围'] }} / {{ detail['报告类型'] }}
          <span v-if="legacyLocator" class="trace-chip">历史定位：{{ legacyLocator }}</span>
        </p>
      </div>
      <button class="btn ghost" data-testid="trace-close" type="button" @click="$emit('close')">关闭</button>
    </div>

    <div class="trace-grid">
      <section class="trace-card">
        <h4>引用状态</h4>
        <dl class="trace-fields">
          <dt>状态</dt>
          <dd data-testid="trace-ref-status">{{ reference?.状态 ?? '尚未迁移' }}</dd>
          <dt>报告编号</dt>
          <dd data-testid="trace-report-no">{{ detail['报告编号'] }}</dd>
          <dt>原始索引号</dt>
          <dd data-testid="trace-index">{{ detail['原始索引号'] || '—' }}</dd>
          <dt>采用审计条目号</dt>
          <dd data-testid="trace-audit-item">{{ detail['采用审计条目号'] || '—' }}</dd>
          <dt>签发来源</dt>
          <dd>{{ reference?.签发来源类型 ?? '—' }}{{ reference?.签发时间 ? `（${reference.签发时间}）` : '' }}</dd>
          <dt>候选索引</dt>
          <dd>{{ (reference?.['候选索引号列表'] ?? []).join('、') || '—' }}</dd>
          <dt>候选审计条目</dt>
          <dd>{{ (reference?.['候选审计条目号列表'] ?? []).join('、') || '—' }}</dd>
          <dt>待核项</dt>
          <dd data-testid="trace-pending">{{ (reference?.['待核项'] ?? []).join('、') || '无' }}</dd>
        </dl>
        <p v-if="!reference" class="trace-hint">
          该报告还未迁移第二版引用，可按目录名与触发来源迁移。
          <button class="btn" data-testid="migrate-this" type="button" :disabled="busy" @click="migrateThis">
            迁移本报告引用
          </button>
        </p>
      </section>

      <section class="trace-card">
        <h4>历史报告原文</h4>
        <p class="trace-body">{{ detail['报告原文'] || '—' }}</p>
        <h4>候选目录（同名不合并）</h4>
        <ul class="trace-list">
          <li v-for="catalog in detail['候选目录']" :key="catalog['索引编号']">
            <strong>{{ catalog['索引编号'] }}</strong> · {{ catalog['目录名称'] }} · {{ catalog['状态'] }}
          </li>
          <li v-if="!detail['候选目录'].length">—</li>
        </ul>
      </section>
    </div>

    <section class="trace-card">
      <h4>审计条目</h4>
      <table class="trace-table">
        <thead>
          <tr><th>审计条目号</th><th>原始索引号</th><th>审计对象</th><th>检查结果</th><th>签发时间</th><th>整改状态</th></tr>
        </thead>
        <tbody>
          <tr v-for="audit in detail['审计条目']" :key="audit.id">
            <td>{{ audit['审计条目号'] || '—' }}</td>
            <td>{{ audit['原始索引号'] || '—' }}</td>
            <td>{{ audit['审计对象'] || '—' }}</td>
            <td>{{ audit['检查结果'] || '—' }}</td>
            <td>{{ audit['签发时间'] || '待核' }}</td>
            <td>{{ audit['整改状态'] || '—' }}</td>
          </tr>
          <tr v-if="!detail['审计条目'].length"><td colspan="6">暂无可引用的审计条目</td></tr>
        </tbody>
      </table>
    </section>

    <section class="trace-card">
      <h4>审计更正</h4>
      <ul class="trace-list">
        <li v-for="item in detail['审计更正']" :key="item.id">
          {{ item['更正编号'] }} · {{ item['更正类型'] }} · {{ item['证明力'] }} ·
          索引 {{ item['原始索引号'] }} / 条目 {{ item['审计条目号'] }} ·
          {{ item['签发时间'] ? `签发 ${item['签发时间']}` : '签发时间待核' }} ·
          {{ item['是否认可'] ? '已认可' : '可引用（未认可）' }}
        </li>
        <li v-if="!detail['审计更正'].length">暂无更正条目</li>
      </ul>
      <form class="trace-form" @submit.prevent="addCorrection">
        <label>
          <span>原始索引号</span>
          <input v-model="correction['原始索引号']" data-testid="correction-index" required />
        </label>
        <label>
          <span>审计条目号</span>
          <input v-model="correction['审计条目号']" data-testid="correction-item" required />
        </label>
        <label>
          <span>更正类型</span>
          <select v-model="correction['更正类型']" data-testid="correction-type">
            <option value="候选归属">候选归属</option>
            <option value="签发时点">签发时点</option>
          </select>
        </label>
        <label>
          <span>签发时间（补足时填写）</span>
          <input v-model="correction['签发时间']" data-testid="correction-issued-at" placeholder="2026-11-02T09:25:00" />
        </label>
        <label class="trace-form-wide">
          <span>说明</span>
          <input v-model="correction['说明']" data-testid="correction-note" placeholder="说明该更正能证明什么" />
        </label>
        <button class="btn" data-testid="submit-correction" type="submit" :disabled="busy">补交审计更正</button>
      </form>
    </section>

    <section class="trace-card">
      <h4>复查处置</h4>
      <p class="trace-sub">
        案件：{{ detail['复查案件']?.['案件编号'] ?? '尚未提交' }} ·
        状态：{{ detail['复查案件']?.['状态'] ?? '待复核' }} ·
        提交次数：{{ detail['复查案件']?.['提交次数'] ?? 0 }}
      </p>
      <form class="trace-form" @submit.prevent="submitReviewAction('复核结案')">
        <label>
          <span>证据来源</span>
          <select v-model="evidenceType" data-testid="evidence-type">
            <option value="">请选择</option>
            <option value="原签发材料">原签发材料</option>
            <option value="后补证据">后补证据</option>
          </select>
        </label>
        <label class="trace-form-wide">
          <span>处置说明</span>
          <input v-model="remark" data-testid="review-remark" placeholder="写明采用的是原签发材料还是后补证据" />
        </label>
        <button class="btn primary" data-testid="submit-review" type="submit" :disabled="busy">提交复核结案</button>
        <button class="btn" data-testid="submit-return" type="button" :disabled="busy" @click="submitReviewAction('发回补证')">
          发回补证
        </button>
      </form>
      <p v-if="message" :class="['trace-message', ok ? '' : 'trace-error']" data-testid="trace-message">{{ message }}</p>
    </section>

    <section class="trace-card">
      <h4>审计处置记录</h4>
      <table class="trace-table">
        <thead>
          <tr><th>处置编号</th><th>类型</th><th>证据来源</th><th>原始索引号</th><th>审计条目号</th><th>待核项</th><th>处置时间</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in detail['审计处置']" :key="item.id">
            <td>{{ item['处置编号'] }}</td>
            <td>{{ item['处置类型'] }}</td>
            <td>{{ item['采用证据类型'] }}</td>
            <td>{{ item['原始索引号'] || '—' }}</td>
            <td>{{ item['采用审计条目号'] || '—' }}</td>
            <td>{{ item['待核项'].join('、') || '无' }}</td>
            <td>{{ item['处置时间'] }}</td>
          </tr>
          <tr v-if="!detail['审计处置'].length"><td colspan="7">暂无处置记录</td></tr>
        </tbody>
      </table>
      <div class="trace-form">
        <button
          v-for="audit in detail['审计条目']"
          :key="`disp-${audit.id}`"
          class="btn"
          type="button"
          :data-testid="`audit-disposition-${audit.id}`"
          :disabled="busy"
          @click="openAudit(audit.id)"
        >
          按引用打开审计处置 · {{ audit['审计条目号'] }}
        </button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import {
  loadReportTrace,
  migrateReports,
  openAuditDisposition,
  submitCorrection,
  submitReview,
  type ReportTraceDetail,
} from '@/api/trace'

const props = defineProps<{ reportId: number }>()
const emit = defineEmits<{ (event: 'close'): void; (event: 'changed'): void }>()

const detail = ref<ReportTraceDetail | null>(null)
const message = ref('')
const ok = ref(true)
const busy = ref(false)
const evidenceType = ref('')
const remark = ref('')
const correction = ref<Record<string, string>>({ '更正类型': '候选归属' })

const reference = computed(() => detail.value?.['报告引用'] ?? null)
const legacyLocator = computed(() => {
  const locator = reference.value?.['来源定位']
  if (!locator) return ''
  return [locator['目录名称'], locator['触发来源']].filter(Boolean).join(' / ')
})

async function reload() {
  try {
    detail.value = await loadReportTrace(props.reportId)
  } catch (error) {
    message.value = error instanceof Error ? error.message : '报告引用读取失败'
    ok.value = false
  }
}

async function migrateThis() {
  busy.value = true
  message.value = ''
  try {
    const result = await migrateReports([props.reportId])
    ok.value = result.ok
    message.value = result.message
    await reload()
    emit('changed')
  } catch (error) {
    ok.value = false
    message.value = error instanceof Error ? error.message : '引用迁移失败'
  } finally {
    busy.value = false
  }
}

async function addCorrection() {
  busy.value = true
  message.value = ''
  try {
    const result = await submitCorrection(props.reportId, { ...correction.value })
    ok.value = result.ok
    message.value = result.message
    await reload()
    emit('changed')
  } catch (error) {
    ok.value = false
    message.value = error instanceof Error ? error.message : '更正提交失败'
  } finally {
    busy.value = false
  }
}

async function submitReviewAction(action: string) {
  busy.value = true
  message.value = ''
  try {
    if (action === '复核结案' && !evidenceType.value) {
      ok.value = false
      message.value = '处置须写明采用的是「原签发材料」还是「后补证据」'
      return
    }
    const result = await submitReview(props.reportId, action, evidenceType.value, remark.value)
    ok.value = result.ok
    message.value = result.message
    await reload()
    emit('changed')
  } catch (error) {
    ok.value = false
    message.value = error instanceof Error ? error.message : '复查提交失败'
  } finally {
    busy.value = false
  }
}

async function openAudit(auditId: number) {
  busy.value = true
  message.value = ''
  try {
    const result = await openAuditDisposition(auditId, props.reportId, evidenceType.value, remark.value)
    ok.value = result.ok
    message.value = result.message
    await reload()
    emit('changed')
  } catch (error) {
    ok.value = false
    message.value = error instanceof Error ? error.message : '审计处置打开失败'
  } finally {
    busy.value = false
  }
}

watch(() => props.reportId, reload, { immediate: true })
</script>

<style scoped>
.trace-panel { display: flex; flex-direction: column; gap: 12px; }
.trace-head { display: flex; justify-content: space-between; align-items: flex-start; }
.trace-sub { color: var(--muted); font-size: 12px; margin: 4px 0 0; }
.trace-chip { margin-left: 8px; padding: 1px 6px; background: #eef2f7; border-radius: 4px; }
.trace-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.trace-card { background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 12px; }
.trace-card h4 { margin: 0 0 8px; font-size: 13px; }
.trace-fields { display: grid; grid-template-columns: 110px 1fr; gap: 4px 8px; margin: 0; font-size: 13px; }
.trace-fields dt { color: var(--muted); }
.trace-fields dd { margin: 0; }
.trace-body { font-size: 13px; line-height: 1.6; margin: 0 0 10px; }
.trace-list { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.8; }
.trace-hint { color: var(--muted); font-size: 12px; }
.trace-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.trace-table th, .trace-table td { border: 1px solid var(--border); padding: 6px 8px; text-align: left; }
.trace-form { display: flex; flex-wrap: wrap; gap: 8px; align-items: flex-end; margin-top: 10px; }
.trace-form label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }
.trace-form input, .trace-form select { padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; }
.trace-form-wide { flex: 1; min-width: 220px; }
.trace-message { font-size: 12px; margin: 8px 0 0; color: #15803d; }
.trace-error { color: #b42318; }
</style>
