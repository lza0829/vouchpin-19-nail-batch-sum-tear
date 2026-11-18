<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import { batchStatus, reconState, STRATEGY_LABELS, BUCKET_LABELS } from '../labels'

const route = useRoute()
const batches = ref([])
const selected = ref(null)
const det = ref(null)
const msg = ref('')
const err = ref('')

async function loadBatches() {
  batches.value = await api.batches()
  if (!selected.value && batches.value.length) {
    const q = Number(route.query.batch)
    selected.value = batches.value.some((b) => b.id === q) ? q : batches.value[0].id
  }
}
async function loadDetail() {
  if (!selected.value) { det.value = null; return }
  err.value = ''
  try { det.value = await api.reconDetail(selected.value) } catch (e) { err.value = e.message }
}
async function act(fn, ok) {
  msg.value = ''; err.value = ''
  try {
    const r = await fn()
    msg.value = ok(r)
    await loadBatches()
    await loadDetail()
  } catch (e) { err.value = e.message }
}
const run = () => act(() => api.reconRun(selected.value),
  (r) => `互证运行 #${r.run_id}：${r.consistent ? '三方一致' : `分叉 ${r.diffs.length} 项`} · 批状态 ${r.batch_status}`)
const override = () => act(() => api.overrideBatch(selected.value),
  (r) => `批头已按事件重算覆盖为 ${r.events.count} 笔 / ${r.events.total}（旧批头已留痕）· 批状态 ${r.batch_status}`)
const unseal = () => act(() => api.unsealBatch(selected.value), () => '已解钉：批内事实回到 open')

watch(selected, loadDetail)
onMounted(async () => {
  try { await loadBatches(); await loadDetail() } catch (e) { err.value = e.message }
})

const s = computed(() => det.value?.summary || null)
const bStatus = computed(() => (det.value ? batchStatus(det.value.batch.status) : null))
const state = computed(() => (s.value ? reconState(s.value.consistent ? 'ok' : 'diverged') : null))
const grouped = computed(() => {
  const g = {}
  for (const d of s.value?.diffs || []) (g[d.bucket] = g[d.bucket] || []).push(d)
  return g
})
</script>
<template>
  <div class="panel">
    <div class="row">
      <label>批次
        <select v-model.number="selected">
          <option v-for="b in batches" :key="b.id" :value="b.id">
            #{{ b.id }} · {{ b.business_day }} · {{ b.status }}
          </option>
        </select>
      </label>
      <button type="button" @click="run" :disabled="!selected">运行互证</button>
      <button type="button" class="ghost" v-if="det?.can_override" @click="override">按事件重算覆盖批头</button>
      <button type="button" class="ghost" v-if="det?.can_unseal" @click="unseal">解钉</button>
    </div>
    <p class="msg" v-if="det">
      当前权威策略：<strong>{{ STRATEGY_LABELS[det.strategy] }}</strong>（全局互斥，于设置页切换）·
      批状态 <span class="tag" :class="bStatus.cls">{{ bStatus.label }}</span>
      <template v-if="det.batch.status === 'disputed' && det.strategy === 'events'">
        · 争议批只读：可「按事件重算覆盖批头」（旧批头留痕），或保持争议——差异修复后重跑互证自动回 sealed
      </template>
      <template v-if="det.strategy === 'batch'"> · 本策略下互证报告只读，不改 sealed 批头；差异未清禁止重钉（解钉类改写除外）</template>
    </p>
    <p class="msg" v-if="msg">{{ msg }}</p>
    <p class="msg err" v-if="err">{{ err }}</p>
  </div>

  <div class="panel" v-if="s">
    <div class="grid">
      <div class="stat"><div class="k">批头（笔数/合计）</div><div class="v">{{ s.header.count }} / <span class="ticket">{{ s.header.total }}</span></div></div>
      <div class="stat"><div class="k">事实汇总（笔数/合计）</div><div class="v">{{ s.facts.count }} / <span class="ticket">{{ s.facts.total }}</span></div></div>
      <div class="stat"><div class="k">事件重算（笔数/合计）</div><div class="v">{{ s.events.count }} / <span class="ticket">{{ s.events.total }}</span></div></div>
      <div class="stat"><div class="k">互证结论</div><div class="v"><span class="tag" :class="state.cls">{{ state.label }}</span></div></div>
    </div>
  </div>

  <div class="panel" v-if="s">
    <div class="desk-head"><h1>差异列表</h1><p>按笔数 / 金额 / 缺事件 / 缺事实分桶；与总览、批状态、互证任务同源</p></div>
    <p class="msg" v-if="!s.diffs.length">三方一致，无差异。</p>
    <div v-for="(list, bucket) in grouped" :key="bucket" class="diff-group">
      <h3><span class="tag bad">{{ BUCKET_LABELS[bucket] || bucket }}</span> × {{ list.length }}</h3>
      <table>
        <thead><tr><th>券码</th><th>事件重算/对方</th><th>批头/事实</th><th>说明</th></tr></thead>
        <tbody>
          <tr v-for="(d, i) in list" :key="i">
            <td>{{ d.coupon_code || '（批头级）' }}</td>
            <td>{{ d.expected ?? '—' }}</td>
            <td>{{ d.actual ?? '—' }}</td>
            <td>{{ d.detail }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <div class="panel" v-if="det">
    <div class="desk-head"><h1>批明细</h1><p>批快照集合内的事实行</p></div>
    <table>
      <thead><tr><th>事实ID</th><th>券码</th><th>活动</th><th>金额</th><th>事件ID</th><th>状态</th></tr></thead>
      <tbody>
        <tr v-for="f in det.facts" :key="f.id">
          <td>{{ f.id }}</td><td>{{ f.coupon_code }}</td><td>{{ f.campaign_code }}</td>
          <td>{{ f.amount }}</td><td>{{ f.event_id }}</td>
          <td><span class="tag warn">{{ f.status }}</span></td>
        </tr>
        <tr v-if="!det.facts.length"><td colspan="6">批内无事实行</td></tr>
      </tbody>
    </table>
  </div>

  <div class="panel" v-if="det">
    <div class="desk-head"><h1>互证运行历史</h1><p>每次任务落库的三方快照</p></div>
    <table>
      <thead><tr><th>运行</th><th>策略</th><th>结论</th><th>批头</th><th>事实</th><th>事件</th><th>时刻</th></tr></thead>
      <tbody>
        <tr v-for="r in det.runs" :key="r.id">
          <td>#{{ r.id }}</td>
          <td>{{ STRATEGY_LABELS[r.strategy] || r.strategy }}</td>
          <td><span class="tag" :class="r.result === 'ok' ? 'ok' : 'bad'">{{ r.result === 'ok' ? '一致' : '分叉' }}</span></td>
          <td>{{ r.header_count }} / {{ r.header_total }}</td>
          <td>{{ r.fact_count }} / {{ r.fact_total }}</td>
          <td>{{ r.event_count }} / {{ r.event_total }}</td>
          <td>{{ r.created_at }}</td>
        </tr>
        <tr v-if="!det.runs.length"><td colspan="7">尚未运行互证任务</td></tr>
      </tbody>
    </table>
  </div>

  <div class="panel" v-if="det && det.audits.length">
    <div class="desk-head"><h1>批头审计</h1><p>事件重算覆盖留下的旧批头</p></div>
    <table>
      <thead><tr><th>ID</th><th>旧批头</th><th>新批头</th><th>原因</th><th>时刻</th></tr></thead>
      <tbody>
        <tr v-for="a in det.audits" :key="a.id">
          <td>#{{ a.id }}</td>
          <td>{{ a.old_fact_count }} / {{ a.old_total_amount }}</td>
          <td>{{ a.new_fact_count }} / {{ a.new_total_amount }}</td>
          <td>{{ a.reason }}</td>
          <td>{{ a.created_at }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
