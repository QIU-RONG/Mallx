<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  adminBrandList,
  adminCategoryTree,
  adminPageProducts,
  adminProductCreate,
  adminProductDelete,
  adminProductUpdate,
} from '../api'
import { useAuthStore } from '../stores/auth'
import type { BrandVO, CategoryVO, ProductVO, SkuCreateDTO } from '../types/api'

const auth = useAuthStore()

const rows = ref<ProductVO[]>([])
const total = ref(0)
const query = reactive({ current: 1, size: 10, keyword: '', status: null as number | null })
const loading = ref(false)

const categories = ref<CategoryVO[]>([])
const brands = ref<BrandVO[]>([])

/** 树拍平后给 el-select 用（父在前，缩进靠 label 前缀区分） */
const flatCategories = computed(() => {
  const out: CategoryVO[] = []
  const walk = (list: CategoryVO[], depth: number) => {
    for (const c of list) {
      out.push({ ...c, name: `${'　'.repeat(depth)}${c.name}` })
      if (c.children?.length) walk(c.children, depth + 1)
    }
  }
  walk(categories.value, 0)
  return out
})

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
}

// ---------- 新增 ----------
const createVisible = ref(false)
const createForm = reactive({
  categoryId: undefined as number | undefined,
  brandId: null as number | null,
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
const editForm = reactive({ id: 0, name: '', subtitle: '', status: 1 })

function openEdit(row: ProductVO) {
  editForm.id = row.id
  editForm.name = row.name
  editForm.subtitle = row.subtitle || ''
  editForm.status = row.status
  editVisible.value = true
}

async function submitEdit() {
  await adminProductUpdate(editForm.id, {
    name: editForm.name,
    subtitle: editForm.subtitle,
    status: editForm.status,
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
  await ElMessageBox.confirm(`确定删除商品「${row.name}」？`, '危险操作', { type: 'warning' }).catch(
    () => null,
  )
  await adminProductDelete(row.id)
  ElMessage.success('已删除（软删）')
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
        <!-- ★ 按钮级权限码：只是体验，真正的边界在后端 @PreAuthorize -->
        <el-button v-if="auth.hasPerm('product:create')" type="success" @click="openCreate">
          新建商品
        </el-button>
      </div>

      <el-table v-loading="loading" :data="rows" border style="margin-top: 12px">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="商品" min-width="200" />
        <el-table-column prop="categoryName" label="分类" width="120" />
        <el-table-column prop="brandName" label="品牌" width="120" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 1 ? 'success' : 'info'">
              {{ row.status === 1 ? '上架' : '下架' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240">
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
        <el-form-item label="名称" required>
          <el-input v-model="createForm.name" maxlength="100" />
        </el-form-item>
        <el-form-item label="副标题">
          <el-input v-model="createForm.subtitle" maxlength="200" />
        </el-form-item>
        <el-form-item label="主图 URL">
          <el-input v-model="createForm.mainImage" placeholder="https://..." />
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
        <el-form-item label="状态">
          <el-radio-group v-model="editForm.status">
            <el-radio :value="1">上架</el-radio>
            <el-radio :value="0">下架</el-radio>
          </el-radio-group>
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
.bar {
  display: flex;
  gap: 10px;
  align-items: center;
}
.skus {
  width: 100%;
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
  color: #909399;
}
</style>
