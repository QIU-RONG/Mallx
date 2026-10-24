<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { regionData } from 'element-china-area-data'
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

/** 弹窗左侧实时预览用：省市区拼一行 */
const regionText = computed(() =>
  [form.province, form.city, form.district].filter(Boolean).join(' '),
)

/** 级联选择器的值：直接绑【名称】数组（props.value = label），省得再查 code → text */
const regionPath = ref<string[]>([])
const cascaderProps = { value: 'label', label: 'label', children: 'children' } as const

function onRegionChange(v: string[] | null) {
  const arr = v ?? []
  form.province = arr[0] ?? ''
  form.city = arr[1] ?? ''
  form.district = arr[2] ?? ''
}

/** 预览里的手机号打码：只有提交时才发全量 */
const maskedPhone = computed(() => {
  const p = form.receiverPhone.trim()
  return p.length === 11 ? `${p.slice(0, 3)} **** ${p.slice(-4)}` : p || '手机号'
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
  regionPath.value = []
}

function openCreate() {
  editingId.value = null
  resetForm()
  dialogVisible.value = true
}

function openEdit(row: AddressVO) {
  editingId.value = row.id
  // 旧数据若不在行政区内（历史手填），级联会显示为空；用户重选即可
  regionPath.value = [row.province, row.city, row.district].filter(Boolean)
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
      width="880px"
      class="addr-dialog"
      :show-close="true"
    >
      <template #header>
        <div class="dlg-head">
          <span class="dlg-ico">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor"
              stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 21s7-5.5 7-11a7 7 0 1 0-14 0c0 5.5 7 11 7 11Z" />
              <circle cx="12" cy="10" r="2.4" />
            </svg>
          </span>
          <div>
            <h4 class="dlg-title">{{ editingId == null ? '新增收货地址' : '编辑收货地址' }}</h4>
            <p class="dlg-sub">填写一次，下单时一键选用；默认地址会排在最前。</p>
          </div>
        </div>
      </template>

      <div class="dlg-grid">
        <!-- 左：实时预览 -->
        <aside class="preview">
          <p class="pv-label">预览</p>
          <div class="pv-card" :class="{ default: form.isDefault }">
            <div class="pv-top">
              <span class="pv-name">{{ form.receiverName || '收货人' }}</span>
              <span class="pv-phone">{{ maskedPhone }}</span>
            </div>
            <p class="pv-region">{{ regionText || '省 / 市 / 区' }}</p>
            <p class="pv-detail">{{ form.detailAddress || '详细地址' }}</p>
            <span v-if="form.isDefault" class="pv-badge">默认</span>
          </div>
          <p class="pv-tip">信息只用于配送，不会对外展示。</p>
        </aside>

        <!-- 右：表单 -->
        <div class="dlg-form">
          <el-form label-position="top" class="addr-form">
            <p class="fsec"><span class="fsec-no">01</span>联系人</p>
            <div class="two">
              <el-form-item label="收货人">
                <el-input v-model="form.receiverName" maxlength="50" placeholder="姓名" />
              </el-form-item>
              <el-form-item label="手机号">
                <el-input v-model="form.receiverPhone" maxlength="11" placeholder="11 位手机号" />
              </el-form-item>
            </div>

            <p class="fsec"><span class="fsec-no">02</span>所在地区</p>
            <el-form-item label="省 / 市 / 区">
              <el-cascader
                v-model="regionPath"
                :options="regionData"
                :props="cascaderProps"
                separator=" / "
                clearable
                filterable
                placeholder="请选择省 / 市 / 区"
                style="width: 100%"
                @change="onRegionChange"
              />
            </el-form-item>

            <p class="fsec"><span class="fsec-no">03</span>详细地址</p>
            <el-form-item>
              <el-input
                v-model="form.detailAddress"
                type="textarea"
                :rows="3"
                maxlength="120"
                show-word-limit
                placeholder="街道、门牌号、楼层 / 房间号"
              />
            </el-form-item>

            <div class="default-row">
              <div>
                <div class="d-title">设为默认地址</div>
                <div class="d-sub">下单时优先使用这一条</div>
              </div>
              <el-switch v-model="form.isDefault" />
            </div>
          </el-form>
        </div>
      </div>

      <template #footer>
        <div class="dlg-footer">
          <button class="cancel-link" type="button" @click="dialogVisible = false">取消</button>
          <el-button type="primary" :loading="saving" @click="submit">保存地址</el-button>
        </div>
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

/* ───── 地址弹窗（Day 68：左预览 + 右表单） ───── */
.dlg-head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
.dlg-ico {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: var(--mx-line-soft);
  color: var(--mx-ink);
  display: flex;
  align-items: center;
  justify-content: center;
  flex: none;
}
.dlg-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--mx-ink);
}
.dlg-sub {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--mx-ink-3);
}
.dlg-grid {
  display: grid;
  grid-template-columns: 260px 1fr;
  gap: 28px;
  margin-top: 4px;
}

/* 左：实时预览 */
.preview {
  padding-top: 4px;
}
.pv-label {
  margin: 0 0 10px;
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--mx-ink-3);
}
.pv-card {
  position: relative;
  border: 1px dashed var(--mx-line);
  border-radius: var(--mx-card-r);
  background: var(--mx-line-soft);
  padding: 18px;
  min-height: 150px;
  transition: border-color 0.18s var(--mx-ease);
}
.pv-card.default {
  border-style: solid;
  border-color: var(--mx-ink);
  background: var(--mx-surface);
}
.pv-top {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}
.pv-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--mx-ink);
}
.pv-phone {
  font-size: 12px;
  color: var(--mx-ink-2);
}
.pv-region {
  margin: 12px 0 4px;
  font-size: 12px;
  color: var(--mx-ink-3);
}
.pv-detail {
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
  color: var(--mx-ink);
  word-break: break-word;
}
.pv-badge {
  position: absolute;
  top: 14px;
  right: 14px;
  font-size: 11px;
  letter-spacing: 0.08em;
  color: var(--mx-accent);
  border: 1px solid var(--mx-accent);
  border-radius: 999px;
  padding: 1px 8px;
}
.pv-tip {
  margin: 12px 0 0;
  font-size: 11px;
  line-height: 1.6;
  color: var(--mx-ink-3);
}

/* 右：表单 */
.fsec {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 4px 0 12px;
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--mx-ink-3);
}
.fsec-no {
  font-family: Georgia, 'Times New Roman', serif;
  color: var(--mx-accent);
  letter-spacing: 0.04em;
}
.addr-form :deep(.el-form-item__label) {
  font-size: 12px;
  color: var(--mx-ink-2);
  padding-bottom: 4px;
}
.addr-form :deep(.el-input__wrapper) {
  background: var(--mx-surface);
  box-shadow: none;
  border: 1px solid var(--mx-line);
  border-radius: 8px;
  padding: 4px 12px;
}
.addr-form :deep(.el-input__wrapper:hover) {
  border-color: var(--mx-ink-3);
}
.addr-form :deep(.el-input__wrapper.is-focus) {
  border-color: var(--mx-ink);
  box-shadow: none;
}
.addr-form :deep(.el-textarea__inner) {
  background: var(--mx-surface);
  box-shadow: none;
  border: 1px solid var(--mx-line);
  border-radius: 8px;
  padding: 10px 12px;
  resize: none;
}
.addr-form :deep(.el-textarea__inner:focus) {
  border-color: var(--mx-ink);
  box-shadow: none;
}
.default-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 8px;
  padding: 14px 16px;
  border: 1px solid var(--mx-line);
  border-radius: var(--mx-card-r);
  background: var(--mx-line-soft);
}
.d-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--mx-ink);
}
.d-sub {
  margin-top: 2px;
  font-size: 12px;
  color: var(--mx-ink-3);
}
.dlg-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 20px;
}
.cancel-link {
  border: none;
  background: transparent;
  padding: 0;
  font-size: 13px;
  color: var(--mx-ink-2);
  cursor: pointer;
}
.cancel-link:hover {
  color: var(--mx-ink);
}

@media (max-width: 760px) {
  .dlg-grid {
    grid-template-columns: 1fr;
    gap: 16px;
  }
  .pv-card {
    min-height: 110px;
  }
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
