<template>
  <div v-if="detail" class="trace-panel">
    <div class="trace-head">
      <div>
        <h3>治理审计处置 · {{ detail['审计条目号'] || detail['记录编号'] }}</h3>
        <p class="trace-sub">
          {{ detail['审计对象'] }} / {{ detail['审计类型'] }} · 原始索引号 {{ detail['原始索引号'] || '—' }}
        </p>
      </div>
      <button class="btn ghost" type="button" @click="$emit('close')">关闭</button>
    </div>

    <section class="trace-card">
      <h4>引用该审计条目的报告</h4>
      <table class="trace-table">
        <thead>
          <tr><th>报告编号</th><th>引用状态</th><th>原始索引号</th><th>签发来源</th><th>待核项</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in detail['报告引用']" :key="item.id">
            <td>{{ item['报告编号'] }}</td>
            <td>{{ item['状态'] }}</td>
            <td>{{ item['原始索引号'] || '—' }}</td>
            <td>{{ item['签发来源类型'] || '—' }}</td>
            <td>{{ item['待核项'].join('、') || '无' }}</td>
          </tr>
          <tr v-if="!detail['报告引用'].length"><td colspan="5">暂无报告引用指向该审计条目</td></tr>
        </tbody>
      </table>
    </section>

    <section class="trace-card">
      <h4>打开实际审计处置</h4>
      <form class="trace-form" @submit.prevent="submit">
        <label>
          <span>报告</span>
          <select v-model="reportId" data-testid="audit-report">
            <option :value="null">按引用自动定位</option>
            <option v-for="item in detail['报告引用']" :key="item.id" :value="item['报告id']">
              {{ item['报告编号'] }}
            </option>
          </select>
        </label>
        <label>
          <span>证据来源</span>
          <select v-model="evidenceType" data-testid="audit-evidence">
            <option value="">按引用记录</option>
            <option value="原签发材料">原签发材料</option>
            <option value="后补证据">后补证据</option>
          </select>
        </label>
        <label class="trace-form-wide">
          <span>处置说明</span>
          <input v-model="remark" placeholder="按可追证报告引用打开处置" />
        </label>
        <button class="btn primary" data-testid="open-audit-disposition" type="submit" :disabled="busy">
          打开处置
        </button>
      </form>
      <p v-if="message" :class="['trace-message', ok ? '' : 'trace-error']" data-testid="audit-message">{{ message }}</p>
    </section>

    <section class="trace-card">
      <h4>处置记录</h4>
      <table class="trace-table">
        <thead>
          <tr><th>处置编号</th><th>报告</th><th>证据来源</th><th>原始索引号</th><th>审计条目号</th><th>处置时间</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in detail['审计处置']" :key="item.id">
            <td>{{ item['处置编号'] }}</td>
            <td>{{ item['报告编号'] }}</td>
            <td>{{ item['采用证据类型'] }}</td>
            <td>{{ item['原始索引号'] || '—' }}</td>
            <td>{{ item['采用审计条目号'] || '—' }}</td>
            <td>{{ item['处置时间'] }}</td>
          </tr>
          <tr v-if="!detail['审计处置'].length"><td colspan="6">暂无处置记录</td></tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

import { loadAuditTrace, openAuditDisposition, type AuditTraceDetail } from '@/api/trace'

const props = defineProps<{ auditId: number }>()
const emit = defineEmits<{ (event: 'close'): void; (event: 'changed'): void }>()

const detail = ref<AuditTraceDetail | null>(null)
const reportId = ref<number | null>(null)
const evidenceType = ref('')
const remark = ref('')
const message = ref('')
const ok = ref(true)
const busy = ref(false)

async function reload() {
  try {
    detail.value = await loadAuditTrace(props.auditId)
  } catch (error) {
    message.value = error instanceof Error ? error.message : '审计引用读取失败'
    ok.value = false
  }
}

async function submit() {
  busy.value = true
  message.value = ''
  try {
    const result = await openAuditDisposition(props.auditId, reportId.value, evidenceType.value, remark.value)
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

watch(() => props.auditId, reload, { immediate: true })
</script>
