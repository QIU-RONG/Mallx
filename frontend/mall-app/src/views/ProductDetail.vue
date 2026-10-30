<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { cartAdd, favoriteAdd, favoriteExists, favoriteRemove, inventoryStock, pageProducts, productDetail, productReviews } from '../api'
import ProductThumb from '../components/ProductThumb.vue'
import type { ProductDetailVO, ProductVO, ReviewVO, SkuVO } from '../types/api'
import { useCartStore } from '../stores/cart'
import { useAuthStore } from '../stores/auth'
import { addViewHistory } from '../utils/history'

const route = useRoute()
const router = useRouter()
const cartStore = useCartStore()
const auth = useAuthStore()
const vo = ref<ProductDetailVO | null>(null)
const mainPic = ref('')
const loading = ref(false)
const chosenSkuId = ref<number | null>(null)
const quantity = ref(1)
const adding = ref(false)

// Day 82：收藏状态（登录后才查）
const faved = ref(false)

async function toggleFavorite() {
  if (!auth.token) {
    ElMessage.warning('登录后才能收藏')
    router.push('/login')
    return
  }
  if (!vo.value) return
  if (faved.value) {
    await favoriteRemove(vo.value.id)
    faved.value = false
    ElMessage.success('已取消收藏')
  } else {
    await favoriteAdd(vo.value.id)
    faved.value = true
    ElMessage.success('已收藏')
  }
}

/** 主图 + 图集合并为可迭代字符串数组（模板里不再碰 undefined） */
const pics = ref<string[]>([])

/** ★ 当前选中的规格对象 —— 价格区/按钮都从它派生，避免模板里到处 find */
const chosenSku = computed<SkuVO | null>(
  () => vo.value?.skus.find((s) => s.id === chosenSkuId.value) ?? null,
)

/** ★ 省了多少钱（有原价且原价更高时才算）—— 「省 ¥300」比「原价 ¥12999」更有说服力 */
const saved = computed(() => {
  const s = chosenSku.value
  if (!s?.originalPrice) return 0
  const diff = Number(s.originalPrice) - Number(s.price)
  return diff > 0 ? diff : 0
})

// ---------------- 库存（Day 73） ----------------
/** skuId → 可售库存；接口只返回存在的 SKU，查不到按 0 处理 */
const stockMap = ref<Record<number, number>>({})
const stock = computed(() => (chosenSkuId.value == null ? 0 : (stockMap.value[chosenSkuId.value] ?? 0)))
const maxQty = computed(() => Math.min(99, Math.max(1, stock.value)))
const soldOut = computed(() => chosenSkuId.value != null && stock.value <= 0)

async function loadStock(ids: number[]) {
  if (!ids.length) return
  try {
    const j = await inventoryStock(ids)
    stockMap.value = j.data || {}
  } catch {
    // ★ 库存查不到时不假装有货，也不阻塞页面：按「未显示库存」处理
    stockMap.value = {}
  }
}

// 换规格时把数量拉回合法范围（原本买了 5 件，换到的规格只剩 2 件）
watch(chosenSkuId, () => {
  if (quantity.value > maxQty.value) quantity.value = maxQty.value
})

// ---------------- 用户评价（Day 61） ----------------
const REVIEW_SIZE = 5
const reviews = ref<ReviewVO[]>([])
const reviewAvg = ref(0)
const reviewCount = ref(0)
const reviewTotal = ref(0)
const reviewPage = ref(1)
const reviewLoading = ref(false)
// Day 88：评价筛选（全部 / 有图 / 5 星 / 4 星）
const reviewFilter = ref<'all' | 'image' | '5' | '4'>('all')

async function loadReviews(reset = false) {
  if (reset) {
    reviewPage.value = 1
    reviews.value = []
  }
  reviewLoading.value = true
  try {
    const filter =
      reviewFilter.value === 'image'
        ? { withImage: true }
        : reviewFilter.value === '5'
          ? { rating: 5 }
          : reviewFilter.value === '4'
            ? { rating: 4 }
            : {}
    const j = await productReviews(route.params.id as string, reviewPage.value, REVIEW_SIZE, filter)
    reviewAvg.value = Number(j.data.avgRating || 0)
    reviewCount.value = j.data.reviewCount
    reviewTotal.value = j.data.total
    reviews.value = reset ? j.data.records : [...reviews.value, ...j.data.records]
  } finally {
    reviewLoading.value = false
  }
}

function changeReviewFilter(f: 'all' | 'image' | '5' | '4') {
  if (reviewFilter.value === f) return
  reviewFilter.value = f
  loadReviews(true)
}

function moreReviews() {
  reviewPage.value += 1
  loadReviews()
}

/** 评价锚点：价格区的「N 条评价 ↓」滚到评价区 */
function jumpToReviews() {
  document.querySelector('.reviews-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

// ---------------- 相关推荐（同分类，排除自己） ----------------
const related = ref<ProductVO[]>([])

async function loadRelated(categoryId?: number, excludeId?: number) {
  try {
    const j = await pageProducts({ current: 1, size: 8, categoryId })
    related.value = (j.data.records || []).filter((p) => p.id !== excludeId).slice(0, 4)
  } catch {
    related.value = []
  }
}

function fmtTime(s?: string) {
  return s ? s.replace('T', ' ').slice(0, 16) : ''
}

onMounted(async () => {
  loading.value = true
  try {
    const j = await productDetail(route.params.id as string)
    vo.value = j.data
    // Day 69：记一条浏览历史（本地，最多 20 条）
    // ★ 价格取第一个 SKU：详情接口的 minPrice 不一定有值（区别于列表的聚合结果）
    addViewHistory({
      id: j.data.id,
      name: j.data.name,
      image: j.data.mainImage,
      price: j.data.skus[0]?.price ?? j.data.minPrice,
    })
    pics.value = [j.data.mainImage, ...j.data.images].filter((x): x is string => !!x)
    mainPic.value = pics.value[0] || ''
    // ★ 规格没有「上下架」字段（后端 SkuVO 只给价格/编码），默认选第一个
    chosenSkuId.value = j.data.skus[0]?.id ?? null
    // 库存单独查：公开接口，失败不阻塞商品主体
    loadStock(j.data.skus.map((s) => s.id))
  } finally {
    loading.value = false
  }
  // ★ 评价与相关推荐是公开接口，不阻塞商品主体渲染
  loadReviews(true)
  if (vo.value) loadRelated(vo.value.categoryId, vo.value.id)
  if (auth.token && vo.value) {
    favoriteExists(vo.value.id).then((r) => (faved.value = !!r.data)).catch(() => (faved.value = false))
  }
})

function pickMain(url: string) {
  mainPic.value = url
}

function pickSku(id: number) {
  chosenSkuId.value = id
}

async function addToCart() {
  if (chosenSkuId.value == null) {
    ElMessage.warning('请选择规格')
    return
  }
  adding.value = true
  try {
    await cartAdd(chosenSkuId.value, quantity.value)
    cartStore.refresh()
    ElMessage.success('已加入购物车')
  } finally {
    adding.value = false
  }
}
</script>

<template>
  <div v-loading="loading" class="detail-wrap">
    <template v-if="vo">
      <el-breadcrumb separator="/" class="crumb">
        <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
        <!-- ★ 分类可点：直接带着 categoryId 回列表，比只显示文字有用 -->
        <el-breadcrumb-item :to="{ path: '/', query: { categoryId: String(vo.categoryId) } }">
          {{ vo.categoryName }}
        </el-breadcrumb-item>
        <el-breadcrumb-item>{{ vo.name }}</el-breadcrumb-item>
      </el-breadcrumb>

      <div class="main">
        <!-- ═══════ 左：图 ═══════ -->
        <div class="gallery">
          <div class="big-wrap">
            <ProductThumb :src="mainPic" :name="vo.name" :seed="vo.id" />
          </div>
          <div v-if="pics.length > 1" class="thumbs">
            <button
              v-for="url in pics"
              :key="url"
              type="button"
              class="thumb"
              :class="{ active: url === mainPic }"
              @click="pickMain(url)"
            >
              <ProductThumb :src="url" :name="vo.name" :seed="vo.id" />
            </button>
          </div>
        </div>

        <!-- ═══════ 右：信息 ═══════ -->
        <div class="info">
          <p class="eyebrow">{{ vo.brandName || 'MALLX' }} · {{ vo.categoryName }}</p>
          <h1 class="title">{{ vo.name }}</h1>
          <p v-if="vo.subtitle" class="subtitle">{{ vo.subtitle }}</p>
          <!-- ★ Day 64：店铺归属（展示层）。没有店铺的商品不显示，而不是写「平台自营」 -->
          <p v-if="vo.shopName" class="shop-line" title="进入店铺" @click="vo.shopId && router.push(`/shop/${vo.shopId}`)">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor"
              stroke-width="1.6" stroke-linejoin="round">
              <path d="M4 9h16v10a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V9Z" />
              <path d="M3 9l1.5-4.5h15L21 9M9 20v-6h6v6" />
            </svg>
            <span class="shop-name">{{ vo.shopName }}</span>
          </p>

          <div class="price-panel">
            <div class="price-main">
              <span class="cur">¥</span>
              <span class="num">{{ chosenSku ? Number(chosenSku.price).toFixed(2) : '-' }}</span>
              <span v-if="saved > 0" class="orig">¥{{ Number(chosenSku?.originalPrice).toFixed(2) }}</span>
            </div>
            <div v-if="saved > 0" class="saved">立省 ¥{{ saved.toFixed(2) }}</div>
            <p class="stock-line" :class="{ out: soldOut }">
              <span v-if="soldOut">该规格暂时缺货</span>
              <span v-else>库存 {{ stock }} 件</span>
            </p>
            <button class="review-link" type="button" @click="jumpToReviews">
              {{ reviewCount }} 条评价 ↓
            </button>
          </div>

          <div class="divider" />

          <p class="sec-label">选择规格</p>
          <div class="skus">
            <button
              v-for="s in vo.skus"
              :key="s.id"
              type="button"
              class="sku"
              :class="{ picked: s.id === chosenSkuId }"
              @click="pickSku(s.id)"
            >
              <span class="sku-name">{{ s.name || s.skuCode }}</span>
              <span class="sku-price">¥{{ Number(s.price).toFixed(2) }}</span>
            </button>
          </div>

          <div class="buy-row">
            <el-input-number v-model="quantity" :min="1" :max="maxQty" />
            <el-button
              class="buy-btn"
              type="primary"
              size="large"
              :loading="adding"
              :disabled="chosenSkuId == null || soldOut"
              @click="addToCart"
            >
              {{ soldOut ? '已售罄' : '加入购物车' }}
            </el-button>
            <button class="link-btn" type="button" @click="router.push('/cart')">
              去购物车结算
            </button>
            <button class="fav-btn" :class="{ on: faved }" type="button" @click="toggleFavorite">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor"
                stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 20s-7-4.6-7-9.6A4.4 4.4 0 0 1 12 7a4.4 4.4 0 0 1 7 3.4c0 5-7 9.6-7 9.6Z" />
              </svg>
              {{ faved ? '已收藏' : '收藏' }}
            </button>
          </div>

          <ul class="promise">
            <li><span class="tick">✓</span>正品保障</li>
            <li><span class="tick">✓</span>极速发货</li>
            <li><span class="tick">✓</span>七天无理由退换</li>
          </ul>
          <p class="delivery-note">下单后 48 小时内发货 · 满 ¥99 免运费 · 支持货到付款</p>
        </div>
      </div>

      <!-- ═══════ 详情 ═══════ -->
      <section class="desc-section">
        <p class="sec-label">商品详情</p>
        <p class="desc-body">{{ vo.description || '（暂无详情）' }}</p>
      </section>

      <!-- ═══════ 用户评价（Day 61） ═══════ -->
      <section class="reviews-section">
        <div class="reviews-head">
          <p class="sec-label">用户评价</p>
          <div class="review-summary">
            <el-rate :model-value="reviewAvg" disabled size="small" />
            <span class="avg mx-serif">{{ reviewAvg.toFixed(1) }}</span>
            <span class="count">{{ reviewCount }} 条评价</span>
          </div>
        </div>

        <div class="review-filters">
          <button type="button" :class="{ on: reviewFilter === 'all' }" @click="changeReviewFilter('all')">全部</button>
          <button type="button" :class="{ on: reviewFilter === 'image' }" @click="changeReviewFilter('image')">有图</button>
          <button type="button" :class="{ on: reviewFilter === '5' }" @click="changeReviewFilter('5')">5 星</button>
          <button type="button" :class="{ on: reviewFilter === '4' }" @click="changeReviewFilter('4')">4 星</button>
        </div>

        <div v-loading="reviewLoading" class="reviews-body">
          <el-empty
            v-if="!reviews.length && !reviewLoading"
            :description="reviewFilter === 'all' ? '还没有评价，买过的人可以说两句' : '没有符合条件的评价'"
          />

          <article v-for="r in reviews" :key="r.id" class="review">
            <div class="avatar">{{ (r.userNickname || '匿').charAt(0) }}</div>
            <div class="review-main">
              <div class="review-top">
                <span class="nick">{{ r.userNickname || '匿名用户' }}</span>
                <el-rate :model-value="r.rating" disabled size="small" />
                <span class="time">{{ fmtTime(r.createdAt) }}</span>
              </div>
              <p class="review-content">{{ r.content || '（未填写文字）' }}</p>
              <!-- Day 80：晒图 -->
              <div v-if="r.images?.length" class="review-imgs">
                <img
                  v-for="(u, i) in r.images"
                  :key="i"
                  :src="u"
                  alt="评价图片"
                  loading="lazy"
                  @error="($event.target as HTMLImageElement).style.display = 'none'"
                />
              </div>
            </div>
          </article>

          <button v-if="reviews.length < reviewTotal" class="more-btn" type="button" @click="moreReviews">
            查看更多评价（{{ reviews.length }} / {{ reviewTotal }}）
          </button>
        </div>
      </section>

      <!-- ═══════ 相关推荐（同分类） ═══════ -->
      <section v-if="related.length" class="related-section">
        <div class="related-head">
          <p class="sec-label">看了又看</p>
          <router-link class="more-link" :to="{ path: '/', query: { categoryId: String(vo.categoryId) } }">
            更多{{ vo.categoryName }} →
          </router-link>
        </div>
        <div class="related-grid">
          <article
            v-for="p in related"
            :key="p.id"
            class="related-card"
            @click="router.push(`/product/${p.id}`)"
          >
            <div class="related-pic">
              <ProductThumb :src="p.mainImage" :name="p.name" :seed="p.id" />
            </div>
            <div class="related-name">{{ p.name }}</div>
            <div v-if="p.minPrice != null" class="related-price mx-serif">
              ¥{{ Number(p.minPrice).toFixed(2) }}
            </div>
          </article>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.detail-wrap {
  max-width: 1200px;
  margin: 0 auto;
  padding: 28px 20px 80px;
  min-height: 300px;
}
.crumb {
  margin-bottom: 28px;
  font-size: 12px;
}
.crumb :deep(.el-breadcrumb__inner) {
  color: var(--mx-ink-3);
  font-weight: 400;
}
.crumb :deep(.el-breadcrumb__item:last-child .el-breadcrumb__inner) {
  color: var(--mx-ink);
}

.main {
  display: flex;
  gap: 56px;
  flex-wrap: wrap;
  align-items: flex-start;
}
.gallery {
  width: 460px;
  flex: none;
}
.big-wrap {
  width: 100%;
  aspect-ratio: 1 / 1;
  border-radius: var(--mx-card-r);
  overflow: hidden;
  border: 1px solid var(--mx-line);
  background: var(--mx-line-soft);
}
.thumbs {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  flex-wrap: wrap;
}
.thumb {
  width: 64px;
  height: 64px;
  padding: 0;
  border: 1px solid var(--mx-line);
  border-radius: var(--mx-media-r);
  overflow: hidden;
  cursor: pointer;
  background: var(--mx-surface);
  transition: border-color 0.18s var(--mx-ease);
}
.thumb.active {
  border-color: var(--mx-ink);
}

.info {
  flex: 1;
  min-width: 320px;
  padding-top: 4px;
}
.eyebrow {
  margin: 0 0 14px;
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--mx-ink-3);
}
.title {
  margin: 0;
  font-size: 30px;
  line-height: 1.35;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--mx-ink);
}
.subtitle {
  margin: 10px 0 0;
  font-size: 14px;
  color: var(--mx-ink-2);
}
.shop-line {
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin: 12px 0 0;
  padding: 4px 10px;
  border: 1px solid var(--mx-line);
  border-radius: 999px;
  font-size: 12px;
  color: var(--mx-ink-2);
  background: var(--mx-surface);
}
.shop-name {
  color: var(--mx-ink);
}

/* ★ 价格不再铺浅色块：一块灰底会把「价格」降级成标签。
   编辑风的做法是让数字自己站出来 —— 大字号 + 衬线 + 上下留白。 */
.price-panel {
  margin-top: 28px;
}
.price-main {
  display: flex;
  align-items: baseline;
  gap: 3px;
  color: var(--mx-ink);
  font-family: Georgia, 'Times New Roman', 'Songti SC', serif;
  font-variant-numeric: tabular-nums;
}
.cur {
  font-size: 18px;
}
.num {
  font-size: 40px;
  line-height: 1.05;
  letter-spacing: -0.01em;
}
.orig {
  margin-left: 12px;
  font-size: 14px;
  color: var(--mx-ink-3);
  text-decoration: line-through;
}
.saved {
  margin-top: 6px;
  font-size: 12px;
  color: var(--mx-accent);
}
.stock-line {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--mx-ink-3);
}
.stock-line.out {
  color: var(--mx-accent);
}

.divider {
  height: 1px;
  background: var(--mx-line);
  margin: 28px 0 24px;
}
.sec-label {
  margin: 0 0 14px;
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--mx-ink-3);
}
.skus {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.sku {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: flex-start;
  min-width: 120px;
  padding: 10px 16px;
  border: 1px solid var(--mx-line);
  border-radius: var(--mx-btn-r);
  background: var(--mx-surface);
  cursor: pointer;
  text-align: left;
  transition:
    border-color 0.18s var(--mx-ease),
    background 0.18s var(--mx-ease);
}
.sku:hover {
  border-color: var(--mx-ink-3);
}
/* ★ 选中 = 反白：墨底白字，不用橙色浅底（浅底在纸感背景上会发脏） */
.sku.picked {
  background: var(--mx-ink);
  border-color: var(--mx-ink);
}
.sku.picked .sku-name,
.sku.picked .sku-price {
  color: #fff;
}
.sku-name {
  font-size: 13px;
  color: var(--mx-ink);
}
.sku-price {
  font-size: 13px;
  font-family: Georgia, 'Times New Roman', serif;
  color: var(--mx-ink-2);
}

.buy-row {
  margin-top: 28px;
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}
.buy-btn {
  min-width: 180px;
  height: 46px;
}
.link-btn {
  border: none;
  background: transparent;
  color: var(--mx-ink-2);
  font-size: 13px;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 4px;
}
.link-btn:hover {
  color: var(--mx-ink);
}
.fav-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 40px;
  padding: 0 14px;
  border: 1px solid var(--mx-line);
  border-radius: var(--mx-btn-r);
  background: var(--mx-surface);
  color: var(--mx-ink-2);
  font-size: 13px;
  cursor: pointer;
}
.fav-btn.on {
  color: var(--mx-accent);
  border-color: var(--mx-accent);
}

.promise {
  margin: 24px 0 0;
  padding: 0;
  list-style: none;
  display: flex;
  gap: 20px;
  font-size: 12px;
  color: var(--mx-ink-2);
}
.promise li {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.tick {
  color: var(--mx-accent);
  font-size: 12px;
}
.delivery-note {
  margin: 12px 0 0;
  font-size: 12px;
  color: var(--mx-ink-3);
}

/* 已下架规格（暂未启用：后端 SkuVO 没有上下架字段，留作扩展） */

/* 价格区旁的「N 条评价 ↓」锚点 */
.review-link {
  display: inline-block;
  margin-top: 10px;
  padding: 0;
  border: none;
  background: transparent;
  font-size: 12px;
  color: var(--mx-ink-3);
  text-decoration: underline;
  text-underline-offset: 3px;
  cursor: pointer;
}
.review-link:hover {
  color: var(--mx-ink);
}

/* ───── 相关推荐 ───── */
.related-section {
  margin-top: 56px;
  padding-top: 32px;
  border-top: 1px solid var(--mx-line);
}
.related-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 18px;
}
.more-link {
  font-size: 12px;
  color: var(--mx-ink-3);
  text-decoration: none;
}
.more-link:hover {
  color: var(--mx-ink);
}
.related-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 22px;
}
.related-card {
  cursor: pointer;
  border: 1px solid var(--mx-line);
  border-radius: var(--mx-card-r);
  background: var(--mx-surface);
  padding: 12px;
  transition:
    border-color 0.18s var(--mx-ease),
    transform 0.18s var(--mx-ease);
}
.related-card:hover {
  border-color: var(--mx-ink-3);
  transform: translateY(-2px);
}
.related-pic {
  aspect-ratio: 4 / 5;
  border-radius: var(--mx-media-r);
  overflow: hidden;
  background: var(--mx-line-soft);
}
.related-name {
  margin-top: 12px;
  font-size: 13px;
  font-weight: 600;
  color: var(--mx-ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.related-price {
  margin-top: 6px;
  font-size: 15px;
  color: var(--mx-ink);
}

@media (max-width: 900px) {
  .related-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.desc-section {
  margin-top: 64px;
  padding-top: 32px;
  border-top: 1px solid var(--mx-line);
}
.desc-body {
  white-space: pre-wrap;
  color: var(--mx-ink-2);
  line-height: 1.9;
  font-size: 14px;
  margin: 0;
  max-width: 760px;
}

/* ───── 用户评价 ───── */
.reviews-section {
  margin-top: 56px;
  padding-top: 32px;
  border-top: 1px solid var(--mx-line);
}
.reviews-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
.review-summary {
  display: flex;
  align-items: center;
  gap: 8px;
}
.review-summary .avg {
  font-size: 22px;
  color: var(--mx-ink);
}
.review-summary .count {
  font-size: 12px;
  color: var(--mx-ink-3);
}
.review-filters {
  display: flex;
  gap: 8px;
  margin: 14px 0 4px;
}
.review-filters button {
  height: 30px;
  padding: 0 14px;
  border: 1px solid var(--mx-line);
  border-radius: 999px;
  background: var(--mx-surface);
  color: var(--mx-ink-2);
  font-size: 12px;
  cursor: pointer;
}
.review-filters button.on {
  border-color: var(--mx-ink);
  background: var(--mx-ink);
  color: #fff;
}
.reviews-body {
  margin-top: 8px;
  min-height: 60px;
}
.review {
  display: flex;
  gap: 14px;
  padding: 20px 0;
  border-bottom: 1px solid var(--mx-line-soft);
}
.avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--mx-line-soft);
  color: var(--mx-ink-2);
  font-family: Georgia, 'Times New Roman', serif;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: none;
}
.review-main {
  flex: 1;
  min-width: 0;
}
.review-top {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.nick {
  font-size: 13px;
  font-weight: 600;
  color: var(--mx-ink);
}
.time {
  margin-left: auto;
  font-size: 12px;
  color: var(--mx-ink-3);
}
.review-content {
  margin: 8px 0 0;
  font-size: 14px;
  line-height: 1.75;
  color: var(--mx-ink-2);
  white-space: pre-wrap;
  word-break: break-word;
}
.review-imgs {
  display: flex;
  gap: 8px;
  margin-top: 10px;
  flex-wrap: wrap;
}
.review-imgs img {
  width: 76px;
  height: 76px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid var(--mx-line);
}
.more-btn {
  margin-top: 18px;
  height: 38px;
  padding: 0 18px;
  border: 1px solid var(--mx-line);
  border-radius: var(--mx-btn-r);
  background: var(--mx-surface);
  color: var(--mx-ink);
  font-size: 13px;
  cursor: pointer;
}
.more-btn:hover {
  border-color: var(--mx-ink-3);
}

@media (max-width: 980px) {
  .gallery {
    width: 100%;
  }
  .main {
    gap: 28px;
  }
  .title {
    font-size: 24px;
  }
  .num {
    font-size: 32px;
  }
}
</style>
