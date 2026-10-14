<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { brandList, cartAdd, categoryTree, pageProducts } from '../api'
import { useAuthStore } from '../stores/auth'
import { useCartStore } from '../stores/cart'
import type { BrandVO, CategoryVO, ProductVO } from '../types/api'

const router = useRouter()
const auth = useAuthStore()
const cartStore = useCartStore()

const records = ref<ProductVO[]>([])
const total = ref(0)
const current = ref(1)
const size = ref(12)
const keyword = ref('')
const categoryId = ref<number | undefined>(undefined)
const brandId = ref<number | undefined>(undefined)
const loading = ref(false)
/** ★ 正在加购的商品 id —— 只让那一张卡转圈，而不是整页 loading */
const addingId = ref<number | null>(null)

const categories = ref<CategoryVO[]>([])
const brands = ref<BrandVO[]>([])

/** 分类树拍平成「id → 名称」与下拉选项（父+子两级全列出，标出层级） */
const catOptions = ref<{ id: number; label: string }[]>([])

function flatten(nodes: CategoryVO[], prefix = '') {
  for (const n of nodes) {
    catOptions.value.push({ id: n.id, label: prefix + n.name })
    if (n.children?.length) flatten(n.children, prefix + n.name + ' / ')
  }
}

/** ★ 当前生效的筛选条件（chips 用）—— 从【状态】推导，而不是另存一份。
 *  另存一份就会出现「下拉框已清、chips 还在」的两份真相。 */
const activeFilters = computed(() => {
  const f: { key: string; label: string; clear: () => void }[] = []
  if (keyword.value) {
    f.push({ key: 'kw', label: `关键词：${keyword.value}`, clear: () => { keyword.value = '' } })
  }
  if (categoryId.value != null) {
    const name = catOptions.value.find((o) => o.id === categoryId.value)?.label ?? String(categoryId.value)
    f.push({ key: 'cat', label: `分类：${name}`, clear: () => { categoryId.value = undefined } })
  }
  if (brandId.value != null) {
    const name = brands.value.find((b) => b.id === brandId.value)?.name ?? String(brandId.value)
    f.push({ key: 'brand', label: `品牌：${name}`, clear: () => { brandId.value = undefined } })
  }
  return f
})

async function load() {
  loading.value = true
  try {
    const j = await pageProducts({
      current: current.value,
      size: size.value,
      categoryId: categoryId.value,
      keyword: keyword.value || undefined,
    })
    let list = j.data.records
    // 后端列表按分类过滤；品牌过滤在 FE1 先前端补刀（页内数据量小），FE2 移到后端
    if (brandId.value != null) list = list.filter((p) => p.brandId === brandId.value)
    records.value = list
    total.value = j.data.total
  } finally {
    loading.value = false
  }
}

function search() {
  current.value = 1
  load()
}

/**
 * ★ 快捷加购（Day 48）：列表卡片直接加进购物车，不用先进详情选规格。
 *
 * <p>加的是 <b>defaultSkuId</b>（后端算好的「最便宜在售 SKU」），
 * 与卡片上显示的「¥x 起」同源 —— 不会出现「看到 9999、加进去 12499」。
 *
 * <p>★ 未登录时【前端先拦】而不是让请求吃 401：
 * http.ts 的 401 处理会清登录态 + 踢到登录页，用户会先看到一句
 * 「请先登录」的报错再被跳走；这里直接给提示并跳转，体验顺一截。
 * （后端那道 401 依然在，前端这层只是「别让他白跑一趟」。）
 */
async function quickAdd(p: ProductVO) {
  if (p.defaultSkuId == null) {
    ElMessage.warning('该商品暂无可购规格')
    return
  }
  if (!auth.token) {
    ElMessage.warning('请先登录')
    router.push('/login')
    return
  }
  addingId.value = p.id
  try {
    await cartAdd(p.defaultSkuId, 1)
    cartStore.refresh()
    ElMessage.success(`已加入购物车：${p.name}`)
  } finally {
    addingId.value = null
  }
}

/** ★ 清掉某一个筛选后要重新查 —— 但「从第 1 页开始查」这件事只做一次，
 *  所以 search() 里把 current 归 1，clearAll 复用同一个入口。 */
function clearAll() {
  keyword.value = ''
  categoryId.value = undefined
  brandId.value = undefined
  search()
}

onMounted(async () => {
  load()
  const [c, b] = await Promise.all([categoryTree(), brandList()])
  categories.value = c.data
  catOptions.value = []
  flatten(c.data)
  brands.value = b.data
})
</script>

<template>
  <div class="list-wrap">
    <div class="filter-bar">
      <el-input
        v-model="keyword"
        placeholder="搜索商品名 / 副标题"
        clearable
        style="width: 240px"
        @keyup.enter="search"
        @clear="search"
      />
      <el-select v-model="categoryId" placeholder="全部分类" clearable style="width: 200px" @change="search">
        <el-option v-for="o in catOptions" :key="o.id" :label="o.label" :value="o.id" />
      </el-select>
      <el-select v-model="brandId" placeholder="全部品牌" clearable style="width: 160px" @change="load">
        <el-option v-for="b in brands" :key="b.id" :label="b.name" :value="b.id" />
      </el-select>
      <el-button type="primary" @click="search">搜索</el-button>
    </div>

    <!-- ★ 筛选 chips：把「当前在按什么筛」变成可见、可逐个撤、可一键清空的状态。
         没有它，用户只能从三个下拉框的文字里反推自己的筛选，清了两个还会以为在筛。 -->
    <div v-if="activeFilters.length" class="chips">
      <span class="chips-label">正在筛选：</span>
      <el-tag
        v-for="f in activeFilters"
        :key="f.key"
        closable
        size="small"
        @close="f.clear(); search()"
      >
        {{ f.label }}
      </el-tag>
      <el-button link type="primary" size="small" @click="clearAll">清除全部</el-button>
    </div>

    <!-- ★ 骨架屏：整块 v-loading 是「一片灰、什么都不能点」，
         骨架屏至少告诉用户「这里会长出卡片、长几个」—— 感知速度差一截。 -->
    <el-skeleton v-if="loading" :rows="3" animated class="grid-skeleton">
      <template #template>
        <div v-for="n in 4" :key="n" class="sk-card">
          <el-skeleton-item variant="image" class="sk-pic" />
          <el-skeleton-item variant="h3" style="width: 80%" />
          <el-skeleton-item variant="text" style="width: 60%" />
        </div>
      </template>
    </el-skeleton>

    <div v-else class="grid">
      <el-card
        v-for="p in records"
        :key="p.id"
        shadow="hover"
        class="card"
        @click="router.push(`/product/${p.id}`)"
      >
        <div class="pic-wrap">
          <img :src="p.mainImage" class="pic" alt="" loading="lazy" />
        </div>
        <div class="name">{{ p.name }}</div>
        <div class="subtitle">{{ p.subtitle }}</div>
        <div class="meta">{{ p.categoryName }} · {{ p.brandName }}</div>
        <!-- ★ 价格：电商列表最该有的数字，此前完全没有（后端 VO 就没这个字段）。
             minPrice 为 null = 没有在售 SKU ⇒ 显示「暂无价格」而不是 ¥0。 -->
        <div class="price-row">
          <template v-if="p.minPrice != null">
            <span class="price">¥{{ Number(p.minPrice).toFixed(2) }}</span>
            <span v-if="p.maxPrice != null && Number(p.maxPrice) > Number(p.minPrice)" class="price-from">
              起
            </span>
          </template>
          <span v-else class="price-none">暂无价格</span>
          <!-- ★ 加购按钮：@click.stop 阻止冒泡到卡片的「进详情」 -->
          <el-button
            class="add-btn"
            type="primary"
            size="small"
            :loading="addingId === p.id"
            :disabled="p.defaultSkuId == null"
            @click.stop="quickAdd(p)"
          >
            加入购物车
          </el-button>
        </div>
        <div class="peek">查看详情 →</div>
      </el-card>

      <!-- ★ 空状态给出路：「没有匹配的商品」+ 一键清筛选，比一句话有用得多 -->
      <el-empty v-if="records.length === 0" description="没有匹配的商品">
        <el-button v-if="activeFilters.length" type="primary" size="small" @click="clearAll">
          清除筛选条件
        </el-button>
      </el-empty>
    </div>

    <el-pagination
      v-model:current-page="current"
      :page-size="size"
      :total="total"
      layout="prev, pager, next"
      @current-change="load"
    />
  </div>
</template>

<style scoped>
.list-wrap {
  max-width: 1200px;
  margin: 0 auto;
  padding: 16px;
}
.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 12px;
}
.chips {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
  padding: 8px 12px;
  background: var(--el-fill-color-light);
  border-radius: var(--brand-radius);
}
.chips-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.grid {
  display: grid;
  /* ★ auto-fill + minmax：窗口宽就多列、窄就少列，不再写死 4 列（窄屏会挤变形） */
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 16px;
  min-height: 200px;
}
.grid-skeleton {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 16px;
}
.sk-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--brand-radius);
  padding: 12px;
}
.sk-pic {
  width: 100%;
  height: 140px;
  margin-bottom: 12px;
}
.card {
  cursor: pointer;
  transition: transform 0.18s ease;
}
/* ★ hover 轻微上浮：比只有阴影多一层「可点」的暗示 */
.card:hover {
  transform: translateY(-3px);
}
.pic-wrap {
  background: var(--el-fill-color-light);
  border-radius: 4px;
  overflow: hidden;
}
.pic {
  width: 100%;
  height: 140px;
  object-fit: cover;
  display: block;
}
.name {
  font-weight: 600;
  margin-top: 8px;
}
.subtitle {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-top: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.meta {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
  margin-top: 6px;
}
/* ★ 价格区：主价用品牌色 + 加大加粗，是整个卡片视觉重心的落点 */
.price-row {
  margin-top: 6px;
  display: flex;
  align-items: center;
  gap: 3px;
}
/* ★ 加购按钮推到最右：不与价格挤在一起，手指/鼠标容易命中 */
.add-btn {
  margin-left: auto;
}
.price {
  color: var(--brand-color);
  font-size: 17px;
  font-weight: 700;
}
.price-from {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.price-none {
  color: var(--el-text-color-placeholder);
  font-size: 13px;
}
/* ★ 默认隐藏、hover 浮现的「查看详情」—— 卡片整体可点这件事，之前没有任何提示 */
.peek {
  margin-top: 8px;
  font-size: 12px;
  color: var(--brand-color);
  opacity: 0;
  transition: opacity 0.18s ease;
}
.card:hover .peek {
  opacity: 1;
}
</style>
