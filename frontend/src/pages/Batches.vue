<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { batchStatus, reconState } from '../labels'

const rows = ref([])
const err = ref('')
async function load() {
  try { rows.value = await api.batches() } catch (e) { err.value = e.message }
}
onMounted(load)
</script>
<template>
  <div class="panel">
    <p class="msg err" v-if="err">{{ err }}</p>
    <table>
      <thead><tr><th>批次</th><th>业务日</th><th>状态</th><th>互证</th><th>笔数</th><th>合计</th><th>钉扎时刻</th><th>最近互证</th><th></th></tr></thead>
      <tbody>
        <tr v-for="b in rows" :key="b.id" :class="{ flag: b.status === 'disputed' || b.recon_state === 'diverged' }">
          <td>{{ b.id }}</td>
          <td>{{ b.business_day }}</td>
          <td><span class="tag" :class="batchStatus(b.status).cls">{{ batchStatus(b.status).label }}</span></td>
          <td><span class="tag" :class="reconState(b.recon_state).cls">{{ reconState(b.recon_state).label }}</span></td>
          <td>{{ b.fact_count }}</td>
          <td>{{ b.total_amount }}</td>
          <td>{{ b.sealed_at }}</td>
          <td>{{ b.last_run_at || '未运行' }}</td>
          <td><router-link class="chip-link" :to="`/recon?batch=${b.id}`">互证详情</router-link></td>
        </tr>
      </tbody>
    </table>
    <p class="msg">互证列与批次互证页、总览现行批同源：分叉批不会显示为完全正常的已钉。</p>
  </div>
</template>
