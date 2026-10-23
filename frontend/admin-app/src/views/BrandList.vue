<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminBrandCreate, adminBrandDelete, adminBrandList, adminBrandUpdate } from '../api'
import { useAuthStore } from '../stores/auth'
import { confirmAction } from '../utils/confirm'
import type { BrandVO } from '../types/api'

/**
 * 品牌管理（Day 54）。
 *
 * <p>★ 管理端与 C 端的口径差异（Day 20 就定下的）：
 * C 端 `GET /api/brands` 只返回 status=1；本页走 `/api/admin/brands`，
 * <b>含停用品牌</b> —— 因为「要重新启用一个品牌，就必须先看得见它」。
 *
 * <p>⚠️ 两个后端约束会以 400 出现，属于正常业务结果：
 * <ul>
 *   <li>`brands.name` 有 UNIQUE —— 重名会被翻译成 400（不是 500）；</li>
 *   <li>删除是物理删：品牌下还有商品（★ 含已软删商品）会被拒。</li>
 * </ul>
 */
const auth = useAuthStore()

const rows = ref<BrandVO[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const r = await adminBrandList()
    rows.value = Array.isArray(r.data) ? r.data : []
  } finally {
    loading.value = false
  }
}

// ---------------- 新增 / 编辑 ----------------
const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({ name: '', logo: '', description: '', status: 1 })

function openCreate() {
  editingId.value = null
  Object.assign(form, { name: '', logo: '', description: '', status: 1 })
  dialogVisible.value = true
}

function openEdit(row: BrandVO) {
  editingId.value = row.id
  Object.assign(form, {
    name: row.name,
    logo: row.logo ?? '',
    description: row.description ?? '',
    status: row.status,
  })
  dialogVisible.value = true
}

async function submit() {
  if (!form.name.trim()) {
    ElMessage.warning('品牌名称不能为空')
    return
  }
  const payload = {
    name: form.name.trim(),
    logo: form.logo.trim() || undefined,
    description: form.description.trim() || undefined,
    status: form.status,
  }
  try {
    if (editingId.value == null) {
      await adminBrandCreate(payload)
      ElMessage.success('品牌已创建')
    } else {
      await adminBrandUpdate(editingId.value, payload)
      ElMessage.success('已保存')
    }
    dialogVisible.value = false
    await load()
  } catch {
    /* 重名 / 无权限：拦截器已提示 */
  }
}

/** 启用 / 停用：走局部更新，只发 status，不动 logo 与简介 */
async function toggleStatus(row: BrandVO) {
  const next = row.status === 1 ? 0 : 1
  try {
    await adminBrandUpdate(row.id, { status: next })
    ElMessage.success(next === 1 ? '已启用（C 端品牌筛选里会重新出现）' : '已停用（C 端不可选）')
    await load()
  } catch {
    /* 拦截器已提示 */
  }
}

async function remove(row: BrandVO) {
  const ok = await confirmAction(
    `确定删除品牌「${row.name}」？\n这是物理删除，且品牌下仍有商品时会被拒绝。` +
      '\n如果只是暂时不用，改成「停用」即可。',
    { title: '删除品牌', confirmButtonText: '删除', type: 'error' },
  )
  if (!ok) return
  try {
    await adminBrandDelete(row.id)
    ElMessage.success('已删除')
    await load()
  } catch {
    /* 有商品引用 / 无权限：拦截器已提示 */
  }
}

onMounted(load)
</script>

<template>
  <el-card shadow="never">
    <div class="bar">
      <span class="stat">共 {{ rows.length }} 个品牌（含停用）</span>
      <el-button v-if="auth.hasPerm('brand:create')" type="primary" @click="openCreate">
        新建品牌
      </el-button>
    </div>

    <el-table v-loading="loading" :data="rows" border stripe style="margin-top: 12px">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column label="Logo" width="90">
        <template #default="{ row }">
          <img v-if="row.logo" :src="row.logo" class="logo" alt="" />
          <span v-else class="logo logo-none">—</span>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="品牌" min-width="160" />
      <el-table-column prop="description" label="简介" min-width="240" show-overflow-tooltip>
        <template #default="{ row }">{{ row.description || '-' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 1 ? 'success' : 'info'">
            {{ row.status === 1 ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button v-if="auth.hasPerm('brand:update')" link type="primary" @click="toggleStatus(row)">
            {{ row.status === 1 ? '停用' : '启用' }}
          </el-button>
          <el-button v-if="auth.hasPerm('brand:update')" link type="primary" @click="openEdit(row)">
            编辑
          </el-button>
          <el-button v-if="auth.hasPerm('brand:delete')" link type="danger" @click="remove(row)">
            删除
          </el-button>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="还没有品牌" />
      </template>
    </el-table>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId == null ? '新建品牌' : '编辑品牌'"
      width="520px"
    >
      <el-form label-width="90px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" maxlength="100" placeholder="例：Apple" />
          <div class="hint">品牌名有唯一约束，重名会保存失败</div>
        </el-form-item>
        <el-form-item label="Logo URL">
          <el-input v-model="form.logo" maxlength="500" placeholder="https://..." />
        </el-form-item>
        <el-form-item label="简介">
          <el-input v-model="form.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="form.status">
            <el-radio :value="1">启用</el-radio>
            <el-radio :value="0">停用</el-radio>
          </el-radio-group>
          <div class="hint">停用后 C 端品牌筛选里不再出现，但商品与历史数据不受影响</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.stat {
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.logo {
  width: 40px;
  height: 40px;
  object-fit: contain;
  border-radius: var(--brand-radius-sm);
  background: var(--el-fill-color-light);
  display: block;
}
.logo-none {
  line-height: 40px;
  text-align: center;
  color: var(--el-text-color-placeholder);
}
.hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
