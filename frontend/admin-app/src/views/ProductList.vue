<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  adminBrandList,
  adminCategoryTree,
  adminPageProducts,
  adminProductCreate,
  adminProductDelete,
  adminProductUpdate,
  adminProductDetail,
  adminProductBatchStatus,
  adminShopList,
} from '../api'
import { useAuthStore } from '../stores/auth'
import { confirmAction } from '../utils/confirm'
import { flattenCategories } from '../utils/tree'
import type { BrandVO, CategoryVO, ProductVO, ShopVO, SkuCreateDTO } from '../types/api'

const auth = useAuthStore()
/** Day 75：商户（带 SHOP_SCOPE_*）看不到店铺选择，店铺由后端按 token 强制 */
const isMerchant = computed(() => auth.perms.some((x) => x.startsWith('SHOP_SCOPE_')))

const rows = ref<ProductVO[]>([])
const selected = ref<ProductVO[]>([])
const total = ref(0)
const query = reactive({ current: 1, size: 10, keyword: '', status: null as number | null })
const loading = ref(false)

const categories = ref<CategoryVO[]>([])
const brands = ref<BrandVO[]>([])
const shops = ref<ShopVO[]>([])

/** 树拍平后给 el-select 用（父在前、子级全角空格缩进）—— 与分类管理页同一个实现 */
const flatCategories = computed(() => flattenCategories(categories.value))

async function load() {
  loading.value = true
  try {
    const j = await adminPageProducts({
      current: query.current,
      size: query.size,
      keyword: query.keyword || undefined,
      // ★ 管理端与 C 端的分水岭：status 不传 = 含下架全都要
      status: query.status,
    })
    rows.value = j.data.records
    total.value = j.data.total
  } finally {
    loading.value = false
  }
}

async function loadDict() {
  // 字典加载失败不阻断主流程（可能没 category:list / brand 权限码）
  try {
    categories.value = (await adminCategoryTree()).data
  } catch {
    categories.value = []
  }
  try {
    const r = await adminBrandList()
    brands.value = Array.isArray(r.data) ? r.data : ((r.data as unknown as { records: BrandVO[] }).records ?? [])
  } catch {
    brands.value = []
  }
  // ★ 店铺字典（Day 64）：商户没有 shop:list 权限，不请求
  if (isMerchant.value) {
    shops.value = []
    return
  }
  try {
    shops.value = (await adminShopList()).data
  } catch {
    shops.value = []
  }
}

/** ★ 清除筛选（空状态里的出路）—— 与 C 端商品列表同一个思路：
 *  空状态不能只告诉用户「没有」，要给他一个「怎么才有」的动作 */
function resetQuery() {
  query.keyword = ''
  query.status = null
  query.current = 1
  load()
}

// ---------- 主图上传（Day 74） ----------
const uploadUrl = '/api/admin/upload/image'
const uploadHeaders = computed(() => ({ Authorization: `Bearer ${auth.token}` }))

function onUploaded(res: { code?: number; message?: string; data?: string }) {
  if (res?.code === 200 && res.data) {
    createForm.mainImage = res.data
    ElMessage.success('图片已上传')
  } else {
    ElMessage.error(res?.message || '上传失败')
  }
}
function onUploadError() {
  ElMessage.error('上传失败（检查格式与大小）')
}

// ---------- 新增 ----------
const createVisible = ref(false)
const createForm = reactive({
  categoryId: undefined as number | undefined,
  brandId: null as number | null,
  shopId: null as number | null,
  name: '',
  subtitle: '',
  mainImage: '',
  status: 1,
  skus: [] as SkuCreateDTO[],
})

function openCreate() {
  Object.assign(createForm, {
    categoryId: undefined,
    brandId: null,
    shopId: null,
    name: '',
    subtitle: '',
    mainImage: '',
    status: 1,
    skus: [{ skuCode: '', price: 1, name: '' }] as SkuCreateDTO[],
  })
  createVisible.value = true
}

function addSku() {
  createForm.skus.push({ skuCode: '', price: 1, name: '' })
}
function removeSku(i: number) {
  createForm.skus.splice(i, 1)
}

async function submitCreate() {
  if (!createForm.categoryId) {
    ElMessage.warning('请选择分类')
    return
  }
  // skuCode 留空的行不下发 —— 后端 @NotBlank 会 400
  const skus = createForm.skus.filter((s) => s.skuCode.trim())
  const id = (await adminProductCreate({
    categoryId: createForm.categoryId,
    brandId: createForm.brandId,
    shopId: isMerchant.value ? undefined : createForm.shopId,
    name: createForm.name,
    subtitle: createForm.subtitle || undefined,
    mainImage: createForm.mainImage || undefined,
    status: createForm.status,
    skus: skus.length ? skus : undefined,
  })).data
  ElMessage.success(`商品已创建，id=${id}`)
  createVisible.value = false
  load()
}

// ---------- 编辑（★ 局部更新：只发要改的字段） ----------
const editVisible = ref(false)
interface EditSku {
  id?: number
  skuCode: string
  name: string
  price: number
  originalPrice?: number | null
  image?: string
}
const editForm = reactive({
  id: 0,
  name: '',
  subtitle: '',
  status: 1,
  shopId: null as number | null,
  skus: [] as EditSku[],
  images: [] as string[],
})

async function openEdit(row: ProductVO) {
  editForm.id = row.id
  editForm.name = row.name
  editForm.subtitle = row.subtitle || ''
  editForm.status = row.status
  editForm.shopId = row.shopId ?? null
  editForm.skus = []
  editForm.images = []
  editVisible.value = true
  const d = (await adminProductDetail(row.id)).data as {
    skus?: Array<{ id: number; skuCode: string; name?: string; price: number; originalPrice?: number | null; image?: string }>
    images?: string[]
  }
  editForm.skus = (d.skus || []).map((s) => ({
    id: s.id,
    skuCode: s.skuCode,
    name: s.name || '',
    price: Number(s.price),
    originalPrice: s.originalPrice ?? undefined,
    image: s.image,
  }))
  editForm.images = [...(d.images || [])]
}

function addEditSku() {
  editForm.skus.push({ skuCode: '', name: '', price: 0, originalPrice: null })
}

function removeEditSku(i: number) {
  editForm.skus.splice(i, 1)
}

function moveImage(i: number, delta: number) {
  const j = i + delta
  if (j < 0 || j >= editForm.images.length) return
  const arr = editForm.images
  ;[arr[i], arr[j]] = [arr[j], arr[i]]
}

async function submitEdit() {
  await adminProductUpdate(editForm.id, {
    name: editForm.name,
    subtitle: editForm.subtitle,
    status: editForm.status,
    shopId: editForm.shopId ?? undefined,
    images: editForm.images,
    skus: editForm.skus.map((s) => ({
      id: s.id,
      skuCode: s.skuCode,
      name: s.name,
      price: s.price,
      originalPrice: s.originalPrice ?? undefined,
      image: s.image,
    })),
  })
  ElMessage.success('已保存')
  editVisible.value = false
  load()
}

// ---------- 上下架 / 删除 ----------
/** ★ 下架 = PUT { status: 0 }；不传 skus 就不会动 SKU（局部更新语义） */
async function toggleStatus(row: ProductVO) {
  const next = row.status === 1 ? 0 : 1
  await adminProductUpdate(row.id, { status: next })
  ElMessage.success(next === 1 ? '已上架' : '已下架')
  load()
}

async function remove(row: ProductVO) {
  // ★ 旧写法 `confirm().catch(() => null)` 会把「取消」也当成继续执行 —— 用了共享工具
  const ok = await confirmAction(`确定删除商品「${row.name}」？删除是软删，可人工恢复。`, {
    title: '删除商品',
    confirmButtonText: '删除',
    type: 'error',
  })
  if (!ok) return
  try {
    await adminProductDelete(row.id)
    ElMessage.success('已删除（软删）')
    await load()
  } catch {
    /* 拦截器已提示 */
  }
}

function exportCsv() {
  if (!rows.value.length) {
    ElMessage.warning('当前页没有商品')
    return
  }
  const head = ['ID', '商品名', '状态', '店铺']
  const lines = rows.value.map((r) =>
    [r.id, r.name, r.status === 1 ? '上架' : '下架', r.shopName ?? '']
      .map((v) => `"${String(v ?? '').replace(/"/g, '""')}"`)
      .join(','),
  )
  const blob = new Blob(['\ufeff' + [head.join(','), ...lines].join('\n')], {
    type: 'text/csv;charset=utf-8',
  })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `products-${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(a.href)
}

function onSelect(rowsSel: ProductVO[]) {
  selected.value = rowsSel
}

async function batchStatus(status: 0 | 1) {
  if (!selected.value.length) {
    ElMessage.warning('先勾选商品')
    return
  }
  await adminProductBatchStatus(
    selected.value.map((r) => r.id),
    status,
  )
  ElMessage.success(status === 1 ? '已批量上架' : '已批量下架')
  selected.value = []
  load()
}

onMounted(() => {
  load()
  loadDict()
})
</script>

<template>
  <div>
    <el-card shadow="never">
      <div class="bar">
        <el-input
          v-model="query.keyword"
          placeholder="商品名称关键词"
          clearable
          style="width: 220px"
          @keyup.enter="load"
          @clear="load"
        />
        <el-select
          v-model="query.status"
          placeholder="状态（不选=全部）"
          clearable
          style="width: 160px"
          @change="load"
        >
          <el-option :value="1" label="仅上架" />
          <el-option :value="0" label="仅下架" />
        </el-select>
        <el-button type="primary" @click="load">查询</el-button>
      <el-button @click="exportCsv">导出 CSV</el-button>
        <!-- ★ 按钮级权限码：只是体验，真正的边界在后端 @PreAuthorize -->
        <el-button v-if="auth.hasPerm('product:create')" type="primary" @click="openCreate">
          新建商品
        </el-button>
      </div>

      <div class="batch-bar">
        <el-button size="small" :disabled="!selected.length" @click="batchStatus(1)">批量上架</el-button>
        <el-button size="small" :disabled="!selected.length" @click="batchStatus(0)">批量下架</el-button>
        <span v-if="selected.length" class="batch-tip">已选 {{ selected.length }} 个</span>
      </div>
      <el-table
        v-loading="loading"
        :data="rows"
        border
        stripe
        style="margin-top: 12px"
        @selection-change="onSelect"
      >
        <el-table-column type="selection" width="44" />
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="图" width="70">
          <template #default="{ row }">
            <img v-if="row.mainImage" :src="row.mainImage" class="thumb" alt="" />
            <span v-else class="thumb thumb-none">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="商品" min-width="180" show-overflow-tooltip />
        <el-table-column prop="categoryName" label="分类" width="120" show-overflow-tooltip />
        <el-table-column prop="brandName" label="品牌" width="110" />
        <el-table-column label="店铺" width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.shopName || '未归属' }}</template>
        </el-table-column>
        <!-- ★ 价格列（Day 48 后端新增 minPrice / maxPrice）：管理端也终于看得到卖多少钱。
             min == max 时只显示一个数，不做无意义的「~」 -->
        <el-table-column label="在售价" width="150" align="right">
          <template #default="{ row }">
            <template v-if="row.minPrice != null">
              <span class="money">
                ¥{{ Number(row.minPrice).toFixed(2) }}
                <template v-if="row.maxPrice != null && Number(row.maxPrice) > Number(row.minPrice)">
                  ~ ¥{{ Number(row.maxPrice).toFixed(2) }}
                </template>
              </span>
            </template>
            <span v-else class="muted">无在售规格</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 1 ? 'success' : 'info'">
              {{ row.status === 1 ? '上架' : '下架' }}
            </el-tag>
          </template>
        </el-table-column>
        <!-- ★ fixed="right"：列一多表格就会横向滚动，操作按钮跟着跑出去 = 用户找不到 -->
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button v-if="auth.hasPerm('product:update')" link type="primary" @click="toggleStatus(row)">
              {{ row.status === 1 ? '下架' : '上架' }}
            </el-button>
            <el-button v-if="auth.hasPerm('product:update')" link type="primary" @click="openEdit(row)">
              编辑
            </el-button>
            <el-button v-if="auth.hasPerm('product:delete')" link type="danger" @click="remove(row)">
              删除
            </el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="没有匹配的商品">
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
    </el-card>

    <!-- 新增 -->
    <el-dialog v-model="createVisible" title="新建商品" width="640px">
      <el-form label-width="90px">
        <el-form-item label="分类" required>
          <el-select v-model="createForm.categoryId" filterable style="width: 100%">
            <el-option v-for="c in flatCategories" :key="c.id" :value="c.id" :label="c.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="品牌">
          <el-select v-model="createForm.brandId" clearable filterable style="width: 100%">
            <el-option v-for="b in brands" :key="b.id" :value="b.id" :label="b.name" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="!isMerchant" label="店铺">
          <el-select v-model="createForm.shopId" clearable filterable style="width: 100%"
            placeholder="不选 = 不归属任何店铺">
            <el-option v-for="s in shops" :key="s.id" :value="s.id" :label="s.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="createForm.name" maxlength="100" />
        </el-form-item>
        <el-form-item label="副标题">
          <el-input v-model="createForm.subtitle" maxlength="200" />
        </el-form-item>
        <el-form-item label="主图">
          <div class="upload-row">
            <img v-if="createForm.mainImage" :src="createForm.mainImage" class="upload-preview" alt="" />
            <div v-else class="upload-preview upload-none">无图</div>
            <el-upload
              :action="uploadUrl"
              :headers="uploadHeaders"
              :show-file-list="false"
              accept="image/jpeg,image/png,image/webp,image/gif"
              :on-success="onUploaded"
              :on-error="onUploadError"
            >
              <el-button>上传图片</el-button>
            </el-upload>
            <el-input v-model="createForm.mainImage" placeholder="或直接粘贴图片 URL" />
          </div>
          <div class="hint">支持 jpg / png / webp / gif，≤ 2MB</div>
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="createForm.status">
            <el-radio :value="1">上架</el-radio>
            <el-radio :value="0">下架</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="SKU">
          <div class="skus">
            <div v-for="(s, i) in createForm.skus" :key="i" class="sku-row">
              <el-input v-model="s.skuCode" placeholder="SKU 编码（必填）" style="width: 180px" />
              <el-input v-model="s.name" placeholder="规格名" style="width: 140px" />
              <el-input-number v-model="s.price" :min="0.01" :precision="2" style="width: 140px" />
              <el-button link type="danger" @click="removeSku(i)">移除</el-button>
            </div>
            <el-button size="small" @click="addSku">+ 添加 SKU</el-button>
            <div class="hint">skuCode 留空的行不会提交；价格必须 &gt; 0（后端 @Positive）</div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 编辑：★ 只改这三个字段，绝不下发 skus，避免误清空规格 -->
    <el-dialog v-model="editVisible" title="编辑商品" width="520px">
      <el-form label-width="90px">
        <el-form-item label="名称">
          <el-input v-model="editForm.name" maxlength="100" />
        </el-form-item>
        <el-form-item label="副标题">
          <el-input v-model="editForm.subtitle" maxlength="200" />
        </el-form-item>
        <el-form-item v-if="!isMerchant" label="店铺">
          <el-select v-model="editForm.shopId" clearable filterable style="width: 100%"
            placeholder="不选 = 保持原归属">
            <el-option v-for="s in shops" :key="s.id" :value="s.id" :label="s.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="editForm.status">
            <el-radio :value="1">上架</el-radio>
            <el-radio :value="0">下架</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="SKU">
          <div class="sku-editor">
            <div v-for="(s, i) in editForm.skus" :key="s.id ?? 'n' + i" class="sku-row">
              <el-input v-model="s.skuCode" placeholder="编码" :disabled="!!s.id" style="width: 130px" />
              <el-input v-model="s.name" placeholder="规格名" style="width: 160px" />
              <el-input-number v-model="s.price" :min="0.01" :precision="2" style="width: 120px" />
              <el-input-number
                v-model="s.originalPrice"
                :min="0"
                :precision="2"
                placeholder="原价"
                style="width: 120px"
              />
              <el-button v-if="!s.id" link type="danger" @click="removeEditSku(i)">删除</el-button>
            </div>
            <el-button size="small" @click="addEditSku">+ 新增 SKU</el-button>
          </div>
        </el-form-item>
        <el-form-item v-if="editForm.images.length" label="图片顺序">
          <div class="img-sort">
            <div v-for="(img, i) in editForm.images" :key="img + i" class="img-item">
              <img :src="img" alt="" />
              <div class="img-btns">
                <el-button link size="small" :disabled="i === 0" @click="moveImage(i, -1)">↑</el-button>
                <el-button link size="small" :disabled="i === editForm.images.length - 1" @click="moveImage(i, 1)">↓</el-button>
              </div>
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.sku-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}
.sku-row {
  display: flex;
  gap: 6px;
  align-items: center;
}
.img-sort {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.img-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}
.img-item img {
  width: 56px;
  height: 56px;
  object-fit: cover;
  border-radius: 4px;
  border: 1px solid var(--el-border-color);
}

.batch-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px;
}
.batch-tip {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.bar {
  display: flex;
  gap: 10px;
  align-items: center;
}
.skus {
  width: 100%;
}
.upload-row {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
}
.upload-preview {
  width: 64px;
  height: 64px;
  object-fit: cover;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  flex: none;
}
.upload-none {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--el-text-color-placeholder);
  font-size: 12px;
  background: var(--el-fill-color-light);
}
.sku-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
.hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
/* ★ 缩略图：列表里能一眼认出是哪个商品，比只看名字快得多 */
.thumb {
  width: 40px;
  height: 40px;
  object-fit: cover;
  border-radius: var(--brand-radius-sm);
  background: var(--el-fill-color-light);
  display: block;
}
.thumb-none {
  width: 40px;
  height: 40px;
  line-height: 40px;
  text-align: center;
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}
/* ★ 金额右对齐 + 等宽数字：一列数字要能上下对齐才看得出量级 */
.money {
  font-variant-numeric: tabular-nums;
  /* ★ 用 --brand-price 而不是品牌色：金额是「信息」，不是「可点的东西」 */
  color: var(--brand-price);
}
.muted {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}
</style>
