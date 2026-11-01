<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { adminAiStats } from '../api'

/**
 * AI 运营（Day 116）：数据由 ai-service 落库（ai_messages），这里只读聚合。
 * 关注四件事：调用量、token 成本、延迟、拒答（有依据率）。
 */
const stats = ref<{
  calls: number
  todayCalls: number
  promptTokens: number
  completionTokens: number
  avgElapsedMs: number
  refusals: number
  refusalRate: number
} | null>(null)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    stats.value = (await adminAiStats()).data
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <div class="toolbar">
      <span class="hint">统计自 ai_messages（含真实模型与 mock 调用）</span>
      <el-button size="small" @click="load">刷新</el-button>
    </div>

    <el-row :gutter="16" style="margin-top: 12px">
      <el-col :span="6">
        <el-card shadow="never"><div class="label">累计调用</div><div class="value">{{ stats?.calls ?? '-' }}</div></el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never"><div class="label">今日调用</div><div class="value">{{ stats?.todayCalls ?? '-' }}</div></el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never"><div class="label">平均耗时</div><div class="value">{{ stats?.avgElapsedMs ?? '-' }} ms</div></el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <div class="label">拒答率</div>
          <div class="value">{{ stats ? Math.round((stats.refusalRate || 0) * 100) : '-' }}%</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="6">
        <el-card shadow="never"><div class="label">Prompt tokens</div><div class="value">{{ stats?.promptTokens ?? '-' }}</div></el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never"><div class="label">Completion tokens</div><div class="value">{{ stats?.completionTokens ?? '-' }}</div></el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never"><div class="label">拒答次数</div><div class="value">{{ stats?.refusals ?? '-' }}</div></el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.value {
  margin-top: 8px;
  font-size: 26px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
</style>
