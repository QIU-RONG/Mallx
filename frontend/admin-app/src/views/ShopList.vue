<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminShopCreate, adminShopList, adminShopUpdate } from '../api'
import { useAuthStore } from '../stores/auth'
import type { ShopVO } from '../types/api'

/**
 * 店铺管理（Day 64，展示层）。
 *
 * <p>★ 只有 列表 / 新建 / 编辑，没有删除：
 * 店铺下可能挂着商品，物理删会让历史商品失去归属说明；不用时「停用」即可。
 *
 * <p>⚠️ 店名 UNIQUE：重名由后端返回 400（不是 500），界面提前写一句。
 */
const auth = useAuthStore()

const rows = ref<ShopVO[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    rows.value = (await adminShopList()).data
  } finally {
    loading.value = false
  }
}

const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({ name: '', logo: '', description: '', status: 1 })

function openCreate() {
  editingId.value = null
  Object.assign(form, { name: '', logo: '', description: '', status: 1 })
  dialogVisible.value = true
}

function openEdit(row: ShopVO) {
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
    ElMessage.warning('店铺名不能为空')
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
      await adminShopCreate(payload)
      ElMessage.success('店铺已创建')
    } else {
      await adminShopUpdate(editingId.value, payload)
      ElMessage.success('已保存')
    }
    dialogVisible.value = false
    await load()
  } catch {
    /* 重名 / 无权限：拦截器已提示 */
  }
}

async function toggleStatus(row: ShopVO) {
  const next = row.status === 1 ? 0 : 1
  try {
    await adminShopUpdate(row.id, { status: next })
    ElMessage.success(next === 1 ? '已启用' : '已停用（仅记录状态，商品详情仍显示所属店铺）')
    await load()
  } catch {
    /* 拦截器已提示 */
  }
}

onMounted(load)
</script>

<template>
  <el-card shadow="never">
    <div class="bar">
      <span class="stat">共 {{ rows.length }} 家店铺（含停用）</span>
      <el-button v-if="auth.hasPerm('shop:create')" type="primary" @click="openCreate">新建店铺</el-button>
    </div>

    <el-table v-loading="loading" :data="rows" border stripe style="margin-top: 12px">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column label="Logo" width="90">
        <template #default="{ row }">
          <img v-if="row.logo" :src="row.logo" class="logo" alt="" />
          <span v-else class="logo logo-none">—</span>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="店铺名" min-width="180" />
      <el-table-column prop="description" label="简介" min-width="260" show-overflow-tooltip>
        <template #default="{ row }">{{ row.description || '-' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 1 ? 'success' : 'info'">
            {{ row.status === 1 ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button v-if="auth.hasPerm('shop:update')" link type="primary" @click="toggleStatus(row)">
            {{ row.status === 1 ? '停用' : '启用' }}
          </el-button>
          <el-button v-if="auth.hasPerm('shop:update')" link type="primary" @click="openEdit(row)">
            编辑
          </el-button>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="还没有店铺" />
      </template>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editingId == null ? '新建店铺' : '编辑店铺'" width="520px">
      <el-form label-width="90px">
        <el-form-item label="店铺名" required>
          <el-input v-model="form.name" maxlength="100" placeholder="例：Apple 官方旗舰店" />
          <div class="hint">店名唯一，重名会保存失败</div>
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
