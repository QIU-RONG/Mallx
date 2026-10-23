<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { brandList, cartAdd, pageProducts } from '../api'
import ProductThumb from '../components/ProductThumb.vue'
import { useAuthStore } from '../stores/auth'
import { useCartStore } from '../stores/cart'
import { useCatalogStore } from '../stores/catalog'
import type { CategoryVO, ProductVO } from '../types/api'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const cartStore = useCartStore()
const catalog = useCatalogStore()

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

const brands = ref<{ id: number; name: string }[]>([])

/** 分类树拍平成「id → 名称」与下拉选项（父+子两级全列出，标出层级） */
const catOptions = ref<{ id: number; label: string }[]>([])

function flatten(nodes: CategoryVO[], prefix = '') {
  for (const n of nodes) {
    catOptions.value.push({ id: n.id, label: prefix + n.name })
    if (n.children?.length) flatten(n.children, prefix + n.name + ' / ')
  }
}

/**
 * ★ 价格拆成「整数 + 小数」两段。
 *
 * <p>官方商城（华为 / 小米 / 京东）全都这么做：整数用大字重、小数用小字。
 * 原因不是花哨 —— 一屏几十个价格并排时，**整数部分对齐**才让眼睛能竖着扫，
 * 否则「¥12999.00」和「¥899.00」的宽度差会把栅格撑得参差不齐。
 */
function splitPrice(v: number | null | undefined): { int: string; dec: string } | null {
  if (v == null) return null
  const s = Number(v).toFixed(2)
  const dot = s.indexOf('.')
  return { int: s.slice(0, dot), dec: s.slice(dot) }
}

type CardRow = ProductVO & { price: { int: string; dec: string } | null }

/** ★ 把「价格拆分」预计算成行数据，而不是在模板里反复调函数（模板里调两次会更难读） */
const rows = computed<CardRow[]>(() =>
  records.value.map((p) => ({ ...p, price: splitPrice(p.minPrice) })),
)

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

/**
 * ★ 从 URL 读筛选条件（顶栏的搜索 / 品类导航就是往 query 里写）。
 *
 * <p>为什么列表页要认 query：顶栏是全局组件，它没法直接改本页的内部状态。
 * 统一「顶栏写 query、列表页读 query」，数据流才是单向的。
 *
 * <p>⚠️ 取舍：**页内**的筛选栏（品牌下拉、chips 的清除）只改本地状态、不回写 URL
 * —— 否则 watch(query) 会被自己的写入再次触发，要额外加防抖标志位才能绕开。
 * 这带来的不一致是：顶栏的品类高亮可能比页内 chips 慢一拍。
 * 判断：这个不一致用户几乎不会遇到（页内筛选与顶栏导航很少交替使用），
 * 而防循环的成本是实打实的，所以先不引入。
 */
function applyQuery() {
  keyword.value = (route.query.kw as string) || ''
  const cid = route.query.categoryId
  categoryId.value = cid != null && cid !== '' ? Number(cid) : undefined
  current.value = 1
  load()
}

// ★ 顶栏点品类 / 搜索时，本页可能已经在 '/' 上（组件不会重建）⇒ 必须 watch query
watch(
  () => route.query,
  () => applyQuery(),
)

function search() {
  current.value = 1
  load()
}

/**
 * ★ 快捷加购：列表卡片直接加进购物车，不用先进详情选规格。
 *
 * <p>加的是 <b>defaultSkuId</b>（后端算好的「最便宜在售 SKU」），
 * 与卡片上显示的「¥x 起」同源 —— 不会出现「看到 9999、加进去 12499」。
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

/** ★ 有没有生效中的筛选 —— 决定要不要展示顶部的促销横幅 */
const hasFilter = computed(() => activeFilters.value.length > 0)

function clearAll() {
  keyword.value = ''
  categoryId.value = undefined
  brandId.value = undefined
  search()
}

/** hero 的唯一动作：滚到商品栅格。★ 不做假按钮 —— 点了必须真的发生点什么 */
function browse() {
  document.querySelector('.grid')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

onMounted(async () => {
  applyQuery()
  // ★ 分类树走 store：顶栏也要它，两边共用一次请求
  const [tree, b] = await Promise.all([catalog.ensure(), brandList()])
  catOptions.value = []
  flatten(tree)
  brands.value = b.data
})
</script>

<template>
  <div class="list-wrap">
    <!-- ★ 首屏（Day 57）：深色整宽段 + 一句立场，替掉原来的浅橙渐变。
         没有运营大图也能成立；将来换真图只需要替换 .hero-art 的背景。 -->
    <section v-if="!hasFilter" class="hero">
      <div class="hero-copy">
        <p class="eyebrow">MALLX SELECTED · 2026</p>
        <h1 class="hero-title">为好产品<br />留一块安静的地方</h1>
        <p class="hero-sub">正品保障 · 极速发货 · 七天无理由退换</p>
        <button class="hero-cta" type="button" @click="browse">开始浏览</button>
      </div>
      <div class="hero-art" aria-hidden="true">
        <span class="ring ring-1" />
        <span class="ring ring-2" />
        <span class="ring ring-3" />
      </div>
    </section>

    <!-- ★ 页内筛选只剩「品牌」和「分类（含子级）」。
         顶栏已经常驻了搜索框和一级品类，这里再放一遍就是同一功能有两个入口 ——
         那种重复在商城里特别容易让人以为「两个搜索不一样」。 -->
    <div class="filter-bar">
      <el-select v-model="categoryId" placeholder="全部分类" clearable style="width: 200px" @change="search">
        <el-option v-for="o in catOptions" :key="o.id" :label="o.label" :value="o.id" />
      </el-select>
      <el-select v-model="brandId" placeholder="全部品牌" clearable style="width: 160px" @change="load">
        <el-option v-for="b in brands" :key="b.id" :label="b.name" :value="b.id" />
      </el-select>
      <div class="spacer" />
      <span class="count">共 {{ total }} 件商品</span>
    </div>

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

    <el-skeleton v-if="loading" :rows="3" animated class="grid-skeleton">
      <template #template>
        <div v-for="n in 8" :key="n" class="sk-card">
          <el-skeleton-item variant="image" class="sk-pic" />
          <el-skeleton-item variant="h3" style="width: 80%" />
          <el-skeleton-item variant="text" style="width: 60%" />
        </div>
      </template>
    </el-skeleton>

    <div v-else class="grid">
      <article
        v-for="p in rows"
        :key="p.id"
        class="card"
        @click="router.push(`/product/${p.id}`)"
      >
        <!-- ★ 图片区 4:5 + 兜底组件：种子图域名解析不了时显示确定性渐变，而不是白框 -->
        <div class="pic-wrap">
          <ProductThumb :src="p.mainImage" :name="p.name" :seed="p.id" />
        </div>

        <div class="name">{{ p.name }}</div>
        <div v-if="p.subtitle" class="subtitle">{{ p.subtitle }}</div>

        <!-- ★ 价格：整数大、小数小（华为/小米/京东都这么做）。
             minPrice 为 null = 没有在售 SKU ⇒ 显示「暂无价格」而不是 ¥0。 -->
        <div class="price-line">
          <template v-if="p.price">
            <span class="sym">¥</span>
            <span class="int">{{ p.price.int }}</span>
            <span class="dec">{{ p.price.dec }}</span>
            <span v-if="p.maxPrice != null && Number(p.maxPrice) > Number(p.minPrice)" class="from">
              起
            </span>
          </template>
          <span v-else class="price-none">暂无价格</span>
        </div>

        <!-- ★ 操作按钮默认【收起】，鼠标移到卡片上才出现 ——
             这是两家商城一致的做法：列表的静止状态只呈现「图 / 名 / 价」，
             把注意力还给商品；按钮在你要动手时才出现。
             ⚠️ 但触屏设备必须常显（见 style 里的 @media (hover)），
             否则「藏在 hover 里的按钮」在手机上等于不存在。 -->
        <div class="card-actions">
          <el-button
            type="primary"
            :loading="addingId === p.id"
            :disabled="p.defaultSkuId == null"
            @click.stop="quickAdd(p)"
          >
            加入购物车
          </el-button>
        </div>
      </article>

      <el-empty v-if="rows.length === 0" description="没有匹配的商品">
        <el-button v-if="activeFilters.length" type="primary" @click="clearAll">
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
  padding: 0 20px 80px;
}
/* ─── 首屏（深色整宽段）───
   ★ 为什么不是渐变横幅：浅橙底 + 白字对比度只有 2 左右，等于「看着很努力但读不清」。
   墨色底 + 白字是同一套令牌里对比度最高的一组，且能立刻把页面分成「品牌区 / 商品区」两段。 */
.hero {
  position: relative;
  overflow: hidden;
  margin: 28px 0 8px;
  padding: 64px 56px;
  border-radius: 12px;
  background: var(--mx-deep);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
}
.hero-copy {
  position: relative;
  z-index: 1;
  max-width: 520px;
}
.eyebrow {
  margin: 0 0 20px;
  font-size: 11px;
  letter-spacing: 0.22em;
  color: rgba(255, 255, 255, 0.55);
}
.hero-title {
  margin: 0;
  font-size: 42px;
  line-height: 1.24;
  font-weight: 500;
  letter-spacing: -0.02em;
}
.hero-sub {
  margin: 18px 0 0;
  font-size: 14px;
  color: rgba(255, 255, 255, 0.66);
}
.hero-cta {
  margin-top: 32px;
  height: 44px;
  padding: 0 26px;
  border: none;
  border-radius: var(--mx-btn-r);
  background: var(--mx-accent);
  color: #fff;
  font-size: 14px;
  letter-spacing: 0.02em;
  cursor: pointer;
  transition: background 0.18s var(--mx-ease);
}
.hero-cta:hover {
  background: #e25c00;
}
/* 右侧三个同心圆：没有大图时，几何图形比留白更像「设计过」 */
.hero-art {
  position: relative;
  width: 320px;
  height: 220px;
  flex: none;
}
.ring {
  position: absolute;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.14);
}
.ring-1 {
  width: 220px;
  height: 220px;
  right: 0;
  top: 0;
  background: radial-gradient(circle at 30% 30%, rgba(255, 103, 0, 0.28), transparent 62%);
}
.ring-2 {
  width: 300px;
  height: 300px;
  right: -40px;
  top: -40px;
}
.ring-3 {
  width: 150px;
  height: 150px;
  right: 35px;
  top: 35px;
  border-color: rgba(255, 255, 255, 0.22);
}
@media (max-width: 900px) {
  .hero {
    padding: 40px 28px;
  }
  .hero-title {
    font-size: 30px;
  }
  .hero-art {
    display: none;
  }
}

.filter-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin: 28px 0 18px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--mx-line);
}
.spacer {
  flex: 1;
}
.count {
  font-size: 12px;
  letter-spacing: 0.04em;
  color: var(--mx-ink-3);
}
.chips {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 20px;
}
.chips-label {
  font-size: 12px;
  color: var(--mx-ink-3);
}

.grid {
  display: grid;
  /* ★ 4 列在 1200 容器里正好，窄屏自动降到 3 / 2 列 */
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 28px 22px;
  min-height: 200px;
}
.grid-skeleton {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 28px 22px;
}
.sk-card {
  border: 1px solid var(--mx-line);
  border-radius: var(--mx-card-r);
  padding: 12px;
}
.sk-pic {
  width: 100%;
  aspect-ratio: 4 / 5;
  height: auto;
  margin-bottom: 14px;
}

/* ─────────── 商品卡片 ───────────
   Day 57：白卡 + 1px 发丝线 + 10px 圆角；hover 只加深边框、上移 2px。
   ★ 不用阴影做常态：白卡铺在纸底上，一条线就够定义边界；阴影会让整页变脏。 */
.card {
  background: var(--mx-surface);
  border: 1px solid var(--mx-line);
  border-radius: var(--mx-card-r);
  padding: 12px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  transition:
    border-color 0.18s var(--mx-ease),
    transform 0.18s var(--mx-ease);
}
.card:hover {
  border-color: var(--mx-ink-3);
  transform: translateY(-2px);
}
.pic-wrap {
  aspect-ratio: 4 / 5;
  border-radius: var(--mx-media-r);
  overflow: hidden;
  background: var(--mx-line-soft);
}
.name {
  margin-top: 14px;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.5;
  letter-spacing: 0.01em;
  color: var(--mx-ink);
  /* ★ 最多两行 + 固定两行高度：长名字不会把同一行的卡片撑得高低不齐 */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 42px;
}
.subtitle {
  margin-top: 6px;
  font-size: 12px;
  color: var(--mx-ink-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ───── 价格：墨色 + 衬线数字 ─────
   ★ 价格不再是红色：红色留给「降价/促销」。在编辑风里，价格用墨色衬线更像目录，
   而不是像警告。整数/小数拆开的做法保留 —— 一列价格能竖向对齐才好扫。 */
.price-line {
  margin-top: auto;
  padding-top: 14px;
  display: flex;
  align-items: baseline;
  gap: 2px;
  color: var(--mx-ink);
  font-family: Georgia, 'Times New Roman', 'Songti SC', serif;
  font-variant-numeric: tabular-nums;
}
.price-line .sym {
  font-size: 13px;
}
.price-line .int {
  font-size: 22px;
  letter-spacing: -0.01em;
}
.price-line .dec {
  font-size: 13px;
}
.price-line .from {
  margin-left: 5px;
  font-size: 12px;
  font-family: inherit;
  color: var(--mx-ink-3);
}
.price-none {
  font-size: 13px;
  color: var(--mx-ink-3);
  font-family: inherit;
}

/* ───── 操作按钮：默认收起，hover 出现 ───── */
.card-actions {
  margin-top: 10px;
  overflow: hidden;
  transition:
    max-height 0.22s ease,
    opacity 0.22s ease;
}
.card-actions :deep(.el-button) {
  width: 100%;
}
/* ★ 只在【确认支持 hover】的设备上才收起 —— 默认常显是更安全的一侧：
   靠 hover 才能点到的按钮，在触屏上等于不存在。 */
@media (hover: hover) {
  .card-actions {
    max-height: 0;
    opacity: 0;
  }
  .card:hover .card-actions {
    max-height: 44px;
    opacity: 1;
  }
}

:deep(.el-pagination) {
  margin-top: 24px;
  justify-content: center;
}
</style>
