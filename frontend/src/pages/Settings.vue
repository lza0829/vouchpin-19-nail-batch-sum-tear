<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { STRATEGY_LABELS } from '../labels'

const day = ref('')
const strategy = ref('events')
const msg = ref('')
const err = ref('')
async function load() {
  try {
    const r = await api.getDay()
    day.value = r.business_day
    const s = await api.getStrategy()
    strategy.value = s.strategy
  } catch (e) { err.value = e.message }
}
async function save() {
  msg.value = ''; err.value = ''
  try {
    const r = await api.setDay(day.value)
    const s = await api.setStrategy(strategy.value)
    msg.value = `业务日已设为 ${r.business_day} · 互证权威策略：${STRATEGY_LABELS[s.strategy]}`
  } catch (e) { err.value = e.message }
}
onMounted(load)
</script>
<template>
  <div class="panel">
    <div class="row">
      <label>业务日 <input v-model="day" placeholder="YYYY-MM-DD" /></label>
      <button type="button" @click="save">保存</button>
    </div>
    <p class="msg" v-if="msg">{{ msg }}</p>
    <p class="msg err" v-if="err">{{ err }}</p>
  </div>
  <div class="panel">
    <div class="desk-head"><h1>钉后互证权威策略</h1><p>全局互斥：任何时刻只贯彻一种，切换即时生效</p></div>
    <label class="radio">
      <input type="radio" v-model="strategy" value="events" />
      <span>
        <strong>以事件湖重算为准</strong><br />
        按批业务日从 redeem/void 事件重算期望合计与笔数；与批头不一致则批标记 disputed，总览不得当正常已钉。
        可按事件重算覆盖批头（旧批头留痕）或保持争议只读；争议期间禁止对该日再钉出第二份现行 sealed。
      </span>
    </label>
    <label class="radio">
      <input type="radio" v-model="strategy" value="batch" />
      <span>
        <strong>以批头+明细为准</strong><br />
        互证报告只读对比事件/事实，分叉只出差异报告（笔数/金额/缺事件/缺事实分桶），不改 sealed 批头；
        差异未清前禁止对该日解钉类改写以外的重钉。
      </span>
    </label>
    <div class="row">
      <button type="button" @click="save">保存策略</button>
    </div>
  </div>
</template>
