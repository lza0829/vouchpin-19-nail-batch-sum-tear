<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { batchStatus, reconState, STRATEGY_LABELS } from '../labels'

const d = ref(null)
const err = ref('')
async function load() {
  err.value = ''
  try { d.value = await api.dashboard() } catch (e) { err.value = e.message }
}
onMounted(load)

const cb = computed(() => d.value?.current_batch || null)
const cbStatus = computed(() => (cb.value ? batchStatus(cb.value.status) : null))
const cbRecon = computed(() => (cb.value ? reconState(cb.value.recon_state) : null))
const alert = computed(() => {
  if (!cb.value) return ''
  if (cb.value.status === 'disputed') return `批 #${cb.value.id} 互证争议中：不得当正常已钉，禁止再钉第二份现行 sealed。`
  if (cb.value.recon_state === 'diverged') return `批 #${cb.value.id} 三方分叉未清，请进入批次互证核对差异。`
  return ''
})
</script>
<template>
  <div class="panel">
    <div class="grid" v-if="d">
      <div class="stat"><div class="k">业务日</div><div class="v">{{ d.business_day }}</div></div>
      <div class="stat"><div class="k">今日事件</div><div class="v">{{ d.event_count }}</div></div>
      <div class="stat"><div class="k">核销事实</div><div class="v ticket">{{ d.fact_count }}</div></div>
      <div class="stat"><div class="k">待钉 open</div><div class="v">{{ d.open_fact_count }}</div></div>
      <div class="stat"><div class="k">今日核销额</div><div class="v ticket">{{ d.redeem_total_today }}</div></div>
      <div class="stat"><div class="k">互证权威策略</div><div class="v strat">{{ STRATEGY_LABELS[d.recon_strategy] || d.recon_strategy }}</div></div>
    </div>
    <p class="msg" v-if="!err">票根洋红标出核销侧数字；钉扎后禁止再写入该日核销。</p>
    <p class="msg err" v-if="err">{{ err }}</p>
  </div>

  <div class="panel" v-if="cb">
    <div class="desk-head">
      <h1>现行批 <span class="mono">#{{ cb.id }}</span></h1>
      <p>业务日 {{ cb.business_day }} · 钉扎于 {{ cb.sealed_at || '—' }}</p>
    </div>
    <div class="grid">
      <div class="stat">
        <div class="k">批状态</div>
        <div class="v"><span class="tag" :class="cbStatus.cls">{{ cbStatus.label }}</span></div>
      </div>
      <div class="stat">
        <div class="k">钉后互证</div>
        <div class="v"><span class="tag" :class="cbRecon.cls">{{ cbRecon.label }}</span></div>
      </div>
      <div class="stat"><div class="k">批头笔数</div><div class="v">{{ cb.fact_count }}</div></div>
      <div class="stat"><div class="k">批头合计</div><div class="v ticket">{{ cb.total_amount }}</div></div>
      <div class="stat"><div class="k">总览来源</div><div class="v">{{ cb.rollup_source || 'header' }}</div></div>
    </div>
    <p class="msg err" v-if="alert">{{ alert }}</p>
    <div class="row">
      <router-link class="chip-link" :to="`/recon?batch=${cb.id}`">进入批次互证 · 差异列表</router-link>
    </div>
  </div>
  <div class="panel" v-else-if="d">
    <p class="msg">本业务日尚无钉扎批。</p>
  </div>
</template>
