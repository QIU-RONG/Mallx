<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { cartAdd, productDetail, productReviews } from '../api'
import ProductThumb from '../components/ProductThumb.vue'
import type { ProductDetailVO, ReviewVO, SkuVO } from '../types/api'
import { useCartStore } from '../stores/cart'

const route = useRoute()
const router = useRouter()
const cartStore = useCartStore()
const vo = ref<ProductDetailVO | null>(null)
const mainPic = ref('')
const loading = ref(false)
const chosenSkuId = ref<number | null>(null)
const quantity = ref(1)
const adding = ref(false)

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

// ---------------- 用户评价（Day 61） ----------------
const REVIEW_SIZE = 5
const reviews = ref<ReviewVO[]>([])
const reviewAvg = ref(0)
const reviewCount = ref(0)
const reviewTotal = ref(0)
const reviewPage = ref(1)
const reviewLoading = ref(false)

async function loadReviews(reset = false) {
  if (reset) {
    reviewPage.value = 1
    reviews.value = []
  }
  reviewLoading.value = true
  try {
    const j = await productReviews(route.params.id as string, reviewPage.value, REVIEW_SIZE)
    reviewAvg.value = Number(j.data.avgRating || 0)
    reviewCount.value = j.data.reviewCount
    reviewTotal.value = j.data.total
    reviews.value = reset ? j.data.records : [...reviews.value, ...j.data.records]
  } finally {
    reviewLoading.value = false
  }
}

function moreReviews() {
  reviewPage.value += 1
  loadReviews()
}

function fmtTime(s?: string) {
  return s ? s.replace('T', ' ').slice(0, 16) : ''
}

onMounted(async () => {
  loading.value = true
  try {
    const j = await productDetail(route.params.id as string)
    vo.value = j.data
    pics.value = [j.data.mainImage, ...j.data.images].filter((x): x is string => !!x)
    mainPic.value = pics.value[0] || ''
    chosenSkuId.value = j.data.skus[0]?.id ?? null
  } finally {
    loading.value = false
  }
  // ★ 评价是公开接口，不阻塞商品主体渲染失败
  loadReviews(true)
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
        <el-breadcrumb-item>{{ vo.categoryName }}</el-breadcrumb-item>
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

          <div class="price-panel">
            <div class="price-main">
              <span class="cur">¥</span>
              <span class="num">{{ chosenSku ? Number(chosenSku.price).toFixed(2) : '-' }}</span>
              <span v-if="saved > 0" class="orig">¥{{ Number(chosenSku?.originalPrice).toFixed(2) }}</span>
            </div>
            <div v-if="saved > 0" class="saved">立省 ¥{{ saved.toFixed(2) }}</div>
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
            <el-input-number v-model="quantity" :min="1" :max="99" />
            <el-button
              class="buy-btn"
              type="primary"
              size="large"
              :loading="adding"
              :disabled="chosenSkuId == null"
              @click="addToCart"
            >
              加入购物车
            </el-button>
            <button class="link-btn" type="button" @click="router.push('/cart')">
              去购物车结算
            </button>
          </div>

          <ul class="promise">
            <li>正品保障</li>
            <li>极速发货</li>
            <li>七天无理由退换</li>
          </ul>
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

        <div v-loading="reviewLoading" class="reviews-body">
          <el-empty v-if="!reviews.length && !reviewLoading" description="还没有评价，买过的人可以说两句" />

          <article v-for="r in reviews" :key="r.id" class="review">
            <div class="avatar">{{ (r.userNickname || '匿').charAt(0) }}</div>
            <div class="review-main">
              <div class="review-top">
                <span class="nick">{{ r.userNickname || '匿名用户' }}</span>
                <el-rate :model-value="r.rating" disabled size="small" />
                <span class="time">{{ fmtTime(r.createdAt) }}</span>
              </div>
              <p class="review-content">{{ r.content || '（未填写文字）' }}</p>
            </div>
          </article>

          <button v-if="reviews.length < reviewTotal" class="more-btn" type="button" @click="moreReviews">
            查看更多评价（{{ reviews.length }} / {{ reviewTotal }}）
          </button>
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

.promise {
  margin: 24px 0 0;
  padding: 0;
  list-style: none;
  display: flex;
  gap: 20px;
  font-size: 12px;
  color: var(--mx-ink-3);
}
.promise li::before {
  content: '·';
  margin-right: 6px;
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
