<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  addressCreate,
  addressDelete,
  addressList,
  addressSetDefault,
  addressUpdate,
} from '../api'
import type { AddressVO } from '../types/api'

/**
 * 收货地址管理（Day 58）。
 *
 * <p>★ 默认地址互斥由<b>后端</b>保证（`PUT /{id}/default` 会把其它地址取消默认），
 * 前端不做「遍历改 isDefault」—— 那会造出两份真相，并发时出现两个默认地址。
 *
 * <p>⚠️ 删除确认用 `then/catch` 转布尔：`confirm().catch(() => null)` 之后继续执行
 * 会把「取消」当成「确认」（管理端 Day 54 修过同一类事故）。
 */
const rows = ref<AddressVO[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    rows.value = (await addressList()).data
  } finally {
    loading.value = false
  }
}

// ---------------- 新增 / 编辑 ----------------
const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const saving = ref(false)

const form = reactive({
  receiverName: '',
  receiverPhone: '',
  province: '',
  city: '',
  district: '',
  detailAddress: '',
  isDefault: false,
})

function resetForm() {
  Object.assign(form, {
    receiverName: '',
    receiverPhone: '',
    province: '',
    city: '',
    district: '',
    detailAddress: '',
    isDefault: rows.value.length === 0,
  })
}

function openCreate() {
  editingId.value = null
  resetForm()
  dialogVisible.value = true
}

function openEdit(row: AddressVO) {
  editingId.value = row.id
  Object.assign(form, {
    receiverName: row.receiverName,
    receiverPhone: row.receiverPhone,
    province: row.province,
    city: row.city,
    district: row.district,
    detailAddress: row.detailAddress,
    isDefault: !!row.isDefault,
  })
  dialogVisible.value = true
}

function validate(): string | null {
  if (!form.receiverName.trim()) return '请填写收货人'
  if (!/^1[3-9]\d{9}$/.test(form.receiverPhone.trim())) return '手机号格式不正确'
  if (!form.province.trim() || !form.city.trim() || !form.district.trim()) return '省 / 市 / 区不能为空'
  if (!form.detailAddress.trim()) return '请填写详细地址'
  return null
}

async function submit() {
  const err = validate()
  if (err) {
    ElMessage.warning(err)
    return
  }
  const payload = {
    receiverName: form.receiverName.trim(),
    receiverPhone: form.receiverPhone.trim(),
    province: form.province.trim(),
    city: form.city.trim(),
    district: form.district.trim(),
    detailAddress: form.detailAddress.trim(),
    isDefault: form.isDefault,
  }
  saving.value = true
  try {
    if (editingId.value == null) {
      await addressCreate(payload)
    } else {
      await addressUpdate(editingId.value, payload)
    }
    ElMessage.success('已保存')
    dialogVisible.value = false
    await load()
  } catch {
    /* 拦截器已提示 */
  } finally {
    saving.value = false
  }
}

async function setDefault(row: AddressVO) {
  if (row.isDefault) return
  try {
    await addressSetDefault(row.id)
    ElMessage.success('已设为默认地址')
    await load()
  } catch {
    /* 拦截器已提示 */
  }
}

async function remove(row: AddressVO) {
  const ok = await ElMessageBox.confirm(
    `确定删除收货人「${row.receiverName}」的这条地址？`,
    '删除地址',
    { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
  )
    .then(() => true)
    .catch(() => false)
  if (!ok) return
  try {
    await addressDelete(row.id)
    ElMessage.success('已删除')
    await load()
  } catch {
    /* 拦截器已提示 */
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="addresses">
    <header class="head">
      <div>
        <h1 class="title">收货地址</h1>
        <p class="sub">下单时从这里选地址；默认地址会排在最前</p>
      </div>
      <el-button type="primary" @click="openCreate">新增地址</el-button>
    </header>

    <el-empty v-if="!rows.length" description="还没有收货地址">
      <el-button type="primary" @click="openCreate">添加第一个地址</el-button>
    </el-empty>

    <div v-else class="grid">
      <article v-for="a in rows" :key="a.id" class="card" :class="{ default: a.isDefault }">
        <div class="card-top">
          <span class="name">{{ a.receiverName }}</span>
          <span class="phone mx-serif">{{ a.receiverPhone }}</span>
          <span v-if="a.isDefault" class="badge">默认</span>
        </div>
        <p class="region">{{ a.province }} {{ a.city }} {{ a.district }}</p>
        <p class="detail">{{ a.detailAddress }}</p>
        <div class="actions">
          <button v-if="!a.isDefault" class="link" type="button" @click="setDefault(a)">
            设为默认
          </button>
          <button class="link" type="button" @click="openEdit(a)">编辑</button>
          <button class="link danger" type="button" @click="remove(a)">删除</button>
        </div>
      </article>
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId == null ? '新增收货地址' : '编辑收货地址'"
      width="560px"
    >
      <el-form label-position="top">
        <div class="two">
          <el-form-item label="收货人">
            <el-input v-model="form.receiverName" maxlength="50" placeholder="姓名" />
          </el-form-item>
          <el-form-item label="手机号">
            <el-input v-model="form.receiverPhone" maxlength="11" placeholder="11 位手机号" />
          </el-form-item>
        </div>
        <div class="three">
          <el-form-item label="省">
            <el-input v-model="form.province" placeholder="如 上海市" />
          </el-form-item>
          <el-form-item label="市">
            <el-input v-model="form.city" placeholder="如 上海市" />
          </el-form-item>
          <el-form-item label="区 / 县">
            <el-input v-model="form.district" placeholder="如 浦东新区" />
          </el-form-item>
        </div>
        <el-form-item label="详细地址">
          <el-input v-model="form.detailAddress" type="textarea" :rows="2" placeholder="街道、门牌号" />
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="form.isDefault">设为默认地址</el-checkbox>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.addresses {
  min-height: 320px;
}
.head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 24px;
  border-bottom: 1px solid var(--mx-line);
}
.title {
  margin: 0;
  font-size: 26px;
  font-weight: 600;
  letter-spacing: -0.01em;
}
.sub {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--mx-ink-2);
}

.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-top: 24px;
}
.card {
  border: 1px solid var(--mx-line);
  border-radius: var(--mx-card-r);
  background: var(--mx-surface);
  padding: 20px;
  transition: border-color 0.18s var(--mx-ease);
}
.card:hover {
  border-color: var(--mx-ink-3);
}
.card.default {
  border-color: var(--mx-ink);
}
.card-top {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.name {
  font-size: 15px;
  font-weight: 600;
  color: var(--mx-ink);
}
.phone {
  font-size: 13px;
  color: var(--mx-ink-2);
}
.badge {
  margin-left: auto;
  font-size: 11px;
  letter-spacing: 0.08em;
  color: var(--mx-accent);
  border: 1px solid var(--mx-accent);
  border-radius: 999px;
  padding: 1px 8px;
}
.region {
  margin: 12px 0 4px;
  font-size: 12px;
  color: var(--mx-ink-3);
}
.detail {
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
  color: var(--mx-ink);
}
.actions {
  display: flex;
  gap: 16px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--mx-line-soft);
}
.link {
  border: none;
  background: transparent;
  padding: 0;
  font-size: 12px;
  color: var(--mx-ink-2);
  cursor: pointer;
}
.link:hover {
  color: var(--mx-ink);
}
.link.danger:hover {
  color: #b3261e;
}

.two {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 16px;
}
.three {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0 12px;
}

@media (max-width: 900px) {
  .grid {
    grid-template-columns: 1fr;
  }
  .three {
    grid-template-columns: 1fr;
  }
}
</style>
