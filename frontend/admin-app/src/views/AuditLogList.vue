<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { adminAuditLogs } from '../api'

/**
 * 操作审计（Day 106）。
 *
 * <p>只做「读」：审计行由后端切面在写操作成功后写入，
 * 前端不提供删除/修改入口 —— 审计日志可改就失去意义。
 */
interface LogRow {
  id: number
  adminName: string
  action: string
  targetType?: string
  targetId?: string
  detail?: string
  createdAt: string
}

const rows = ref<LogRow[]>([])
const total = ref(0)
const loading = ref(false)
const query = reactive({ page: 1, size: 10, action: '', adminName: '' })

async function load() {
  loading.value = true
  try {
    const j = await adminAuditLogs({
      page: query.page,
      size: query.size,
      action: query.action.trim() || undefined,
      adminName: query.adminName.trim() || undefined,
    })
    rows.value = j.data.records
    total.value = j.data.total
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="toolbar">
      <el-input v-model="query.action" placeholder="动作（如 商品编辑）" clearable style="width: 200px" />
      <el-input v-model="query.adminName" placeholder="操作人" clearable style="width: 160px" />
      <el-button type="primary" @click="load">查询</el-button>
    </div>

    <el-table v-loading="loading" :data="rows" border stripe style="margin-top: 12px">
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="createdAt" label="时间" width="200" />
      <el-table-column prop="adminName" label="操作人" width="140" />
      <el-table-column prop="action" label="动作" width="150" />
      <el-table-column label="对象" width="160">
        <template #default="{ row }">
          {{ row.targetType || '-' }}<span v-if="row.targetId"> #{{ row.targetId }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="detail" label="详情" min-width="320" show-overflow-tooltip />
      <template #empty>
        <el-empty description="还没有审计记录（写操作成功后自动记录）" />
      </template>
    </el-table>

    <el-pagination
      v-model:current-page="query.page"
      :page-size="query.size"
      :total="total"
      layout="total, prev, pager, next"
      style="margin-top: 12px"
      @current-change="load"
    />
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  gap: 8px;
}
</style>
