<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminUserDetail, adminUserPage, adminUserUpdateStatus } from '../api'
import { useAuthStore } from '../stores/auth'
import { confirmAction } from '../utils/confirm'
import type { UserVO } from '../types/api'

/**
 * 用户管理（Day 54）。
 *
 * <p>★ 与 C 端 `GET /api/users/me` 的分工：那边只能看「我」，这边看全部 ——
 * 防线是权限码 `user:list`（菜单也按它显隐），不是归属过滤。
 *
 * <p>⚠️ `user:status`（禁用账号）在种子里<b>只发给超管</b>：这是治理动作。
 * 订单管理员能看用户列表、能看详情，但没有这个按钮 —— 这正是「每个端点一个码」的意义。
 */
const auth = useAuthStore()

const rows = ref<UserVO[]>([])
const total = ref(0)
const loading = ref(false)
const query = reactive({ current: 1, size: 10, keyword: '', status: null as number | null })

async function load() {
  loading.value = true
  try {
    const j = await adminUserPage({
      current: query.current,
      size: query.size,
      keyword: query.keyword || undefined,
      status: query.status,
    })
    rows.value = j.data.records
    total.value = j.data.total
  } finally {
    loading.value = false
  }
}

function exportCsv() {
  if (!rows.value.length) {
    ElMessage.warning('当前页没有用户')
    return
  }
  const head = ['ID', '用户名', '昵称', '手机号', '邮箱', '状态', '注册时间']
  const lines = rows.value.map((r) =>
    [
      r.id, r.username, r.nickname ?? '', r.phone ?? '', r.email ?? '',
      r.status === 1 ? '正常' : '已禁用', r.createdAt ?? '',
    ]
      .map((v) => `"${String(v ?? '').replace(/"/g, '""')}"`)
      .join(','),
  )
  const blob = new Blob(['\ufeff' + [head.join(','), ...lines].join('\n')], {
    type: 'text/csv;charset=utf-8',
  })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `users-${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(a.href)
}

function search() {
  query.current = 1
  load()
}

function resetQuery() {
  query.keyword = ''
  query.status = null
  search()
}

// ---------------- 详情 ----------------
const detailVisible = ref(false)
const detail = ref<UserVO | null>(null)

async function openDetail(row: UserVO) {
  try {
    detail.value = (await adminUserDetail(row.id)).data
    detailVisible.value = true
  } catch {
    /* 没有 user:detail：拦截器已提示 */
  }
}

/**
 * ★ 禁用要写清「会发生什么」：token 未过期前接口仍可用（后端只校验 token 合法性），
 * 但下次登录会被拒。这一点不写出来，运营会以为「点了立刻踢下线」。
 */
async function toggleStatus(row: UserVO) {
  const next = row.status === 1 ? 0 : 1
  const ok = await confirmAction(
    next === 0
      ? `确定禁用用户「${row.nickname || row.username}」？\n禁用后该账号无法再登录；已签发的 token 在过期前仍然有效。`
      : `确定恢复用户「${row.nickname || row.username}」的登录权限？`,
    {
      title: next === 0 ? '禁用账号' : '启用账号',
      confirmButtonText: next === 0 ? '禁用' : '启用',
      type: next === 0 ? 'error' : 'warning',
    },
  )
  if (!ok) return
  try {
    await adminUserUpdateStatus(row.id, next)
    ElMessage.success(next === 1 ? '已启用' : '已禁用')
    await load()
  } catch {
    /* 无 user:status：拦截器已提示 */
  }
}

onMounted(load)
</script>

<template>
  <el-card shadow="never">
    <div class="bar">
      <el-input
        v-model="query.keyword"
        placeholder="用户名 / 昵称 / 手机号"
        clearable
        style="width: 240px"
        @keyup.enter="search"
        @clear="search"
      />
      <el-select
        v-model="query.status"
        placeholder="状态（不选=全部）"
        clearable
        style="width: 150px"
        @change="search"
      >
        <el-option :value="1" label="正常" />
        <el-option :value="0" label="已禁用" />
      </el-select>
      <el-button type="primary" @click="search">查询</el-button>
      <el-button @click="exportCsv">导出 CSV</el-button>
    </div>

    <el-table v-loading="loading" :data="rows" border stripe style="margin-top: 12px">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="username" label="用户名" min-width="140" />
      <el-table-column prop="nickname" label="昵称" min-width="120">
        <template #default="{ row }">{{ row.nickname || '-' }}</template>
      </el-table-column>
      <el-table-column prop="phone" label="手机号" width="140">
        <template #default="{ row }">{{ row.phone || '-' }}</template>
      </el-table-column>
      <el-table-column prop="email" label="邮箱" min-width="180">
        <template #default="{ row }">{{ row.email || '-' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 1 ? 'success' : 'danger'">
            {{ row.status === 1 ? '正常' : '已禁用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="createdAt" label="注册时间" width="180" />
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button v-if="auth.hasPerm('user:detail')" link type="primary" @click="openDetail(row)">
            详情
          </el-button>
          <el-button
            v-if="auth.hasPerm('user:status')"
            link
            :type="row.status === 1 ? 'danger' : 'success'"
            @click="toggleStatus(row)"
          >
            {{ row.status === 1 ? '禁用' : '启用' }}
          </el-button>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="没有匹配的用户">
          <el-button v-if="query.keyword || query.status != null" size="small" @click="resetQuery">
            清除筛选
          </el-button>
        </el-empty>
      </template>
    </el-table>

    <el-pagination
      v-model:current-page="query.current"
      v-model:page-size="query.size"
      :total="total"
      layout="total, prev, pager, next"
      style="margin-top: 12px"
      @current-change="load"
    />

    <el-dialog v-model="detailVisible" :title="`用户详情 #${detail?.id ?? ''}`" width="520px">
      <el-descriptions v-if="detail" :column="1" border>
        <el-descriptions-item label="ID">{{ detail.id }}</el-descriptions-item>
        <el-descriptions-item label="用户名">{{ detail.username }}</el-descriptions-item>
        <el-descriptions-item label="昵称">{{ detail.nickname || '-' }}</el-descriptions-item>
        <el-descriptions-item label="手机号">{{ detail.phone || '-' }}</el-descriptions-item>
        <el-descriptions-item label="邮箱">{{ detail.email || '-' }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          {{ detail.status === 1 ? '正常' : '已禁用' }}
        </el-descriptions-item>
        <el-descriptions-item label="注册时间">{{ detail.createdAt || '-' }}</el-descriptions-item>
      </el-descriptions>
      <div class="hint">
        ★ 出参是 UserVO：只有可公开字段，<b>不含密码哈希</b>（Day 22 修掉的越权漏洞）。
      </div>
    </el-dialog>
  </el-card>
</template>

<style scoped>
.bar {
  display: flex;
  gap: 10px;
  align-items: center;
}
.hint {
  margin-top: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
