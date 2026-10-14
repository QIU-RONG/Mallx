<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { cartAdd, productDetail } from '../api'
import type { ProductDetailVO, SkuVO } from '../types/api'
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
})

function pickMain(url: string) {
  mainPic.value = url
}

/** ★ 换规格时把数量夹回合法范围 —— 否则会出现「选了大码还在 99 件」这种越界组合 */
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
        <div class="gallery">
          <!-- ★ 主图包一层占位底色：图没加载出来时不是一片白，而是浅灰块 -->
          <div class="big-wrap">
            <img :src="mainPic" class="big" alt="" />
          </div>
          <div class="thumbs">
            <img
              v-for="url in pics"
              :key="url"
              :src="url"
              class="thumb"
              :class="{ active: url === mainPic }"
              @click="pickMain(url)"
              alt=""
            />
          </div>
        </div>

        <div class="info">
          <h2 class="title">{{ vo.name }}</h2>
          <p class="subtitle">{{ vo.subtitle }}</p>

          <div class="tags">
            <el-tag v-if="vo.brandName" type="info" effect="plain" size="small">{{ vo.brandName }}</el-tag>
            <el-tag v-if="vo.categoryName" type="info" effect="plain" size="small">{{ vo.categoryName }}</el-tag>
          </div>

          <!-- ★ 价格区：整页的视觉重心。选中哪个规格，这里就显示哪个的价格 ——
               之前价格只藏在 SKU 小卡片里，用户得自己找 -->
          <div class="price-panel">
            <div class="price-main">
              <span class="cur">¥</span>
              <span class="num">{{ chosenSku ? Number(chosenSku.price).toFixed(2) : '-' }}</span>
              <span v-if="saved > 0" class="orig">¥{{ Number(chosenSku?.originalPrice).toFixed(2) }}</span>
            </div>
            <div v-if="saved > 0" class="saved">立省 ¥{{ saved.toFixed(2) }}</div>
          </div>

          <h4 class="sec-title">选择规格</h4>
          <div class="skus">
            <div
              v-for="s in vo.skus"
              :key="s.id"
              class="sku"
              :class="{ picked: s.id === chosenSkuId }"
              @click="pickSku(s.id)"
            >
              <div class="sku-name">{{ s.name || s.skuCode }}</div>
              <div class="sku-price">¥{{ Number(s.price).toFixed(2) }}</div>
              <div v-if="s.originalPrice" class="sku-orig">¥{{ Number(s.originalPrice).toFixed(2) }}</div>
            </div>
          </div>

          <div class="buy-row">
            <span class="qty-label">数量</span>
            <el-input-number v-model="quantity" :min="1" :max="99" />
            <el-button
              type="primary"
              size="large"
              :loading="adding"
              :disabled="chosenSkuId == null"
              @click="addToCart"
            >
              加入购物车
            </el-button>
            <el-button size="large" @click="router.push('/cart')">去购物车结算</el-button>
          </div>
        </div>
      </div>

      <el-card shadow="never" class="desc-card">
        <template #header>
          <span class="desc-title">商品详情</span>
        </template>
        <p class="desc-body">{{ vo.description || '（暂无详情）' }}</p>
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.detail-wrap {
  max-width: 1100px;
  margin: 0 auto;
  padding: 16px;
  min-height: 300px;
}
.crumb {
  margin-bottom: 16px;
}
.main {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
}
.gallery {
  width: 380px;
  flex: none;
}
/* ★ 主图占位底：图未加载时是浅灰块，不是刺眼的纯白 */
.big-wrap {
  width: 380px;
  height: 380px;
  border-radius: var(--brand-radius);
  overflow: hidden;
  background: var(--el-fill-color-light);
}
.big {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.thumbs {
  display: flex;
  gap: 8px;
  margin-top: 8px;
  flex-wrap: wrap;
}
.thumb {
  width: 56px;
  height: 56px;
  object-fit: cover;
  border: 2px solid transparent;
  border-radius: var(--brand-radius-sm);
  cursor: pointer;
  background: var(--el-fill-color-light);
  transition: border-color 0.15s ease;
}
.thumb.active {
  border-color: var(--brand-color);
}
.info {
  flex: 1;
  min-width: 300px;
}
.title {
  margin: 0;
  font-size: 22px;
  line-height: 1.35;
}
.subtitle {
  color: var(--el-text-color-secondary);
  margin: 8px 0 12px;
}
.tags {
  display: flex;
  gap: 6px;
  margin-bottom: 16px;
}
/* ★ 价格面板：浅色底 + 圆角，把「多少钱」从一堆文字里拎出来 */
.price-panel {
  background: var(--el-fill-color-light);
  border-radius: var(--brand-radius);
  padding: 14px 18px;
  margin-bottom: 20px;
}
.price-main {
  display: flex;
  align-items: baseline;
  gap: 2px;
}
.cur {
  color: var(--brand-color);
  font-size: 18px;
  font-weight: 700;
}
.num {
  color: var(--brand-color);
  font-size: 30px;
  font-weight: 800;
  line-height: 1.1;
}
.orig {
  margin-left: 10px;
  color: var(--el-text-color-placeholder);
  text-decoration: line-through;
  font-size: 14px;
}
.saved {
  margin-top: 4px;
  color: var(--brand-color-dark);
  font-size: 12px;
}
.sec-title {
  margin: 0 0 10px;
}
.skus {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.sku {
  border: 2px solid var(--el-border-color-lighter);
  border-radius: var(--brand-radius);
  padding: 8px 14px;
  cursor: pointer;
  transition: all 0.15s ease;
  min-width: 96px;
  text-align: center;
}
.sku:hover {
  border-color: var(--brand-color-light);
}
.sku.picked {
  border-color: var(--brand-color);
  background: #fff7f0;
}
.sku-name {
  font-size: 13px;
}
.sku-price {
  color: var(--brand-color);
  font-weight: 700;
  margin-top: 2px;
}
.sku-orig {
  color: var(--el-text-color-placeholder);
  text-decoration: line-through;
  font-size: 12px;
}
.buy-row {
  margin-top: 24px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.qty-label {
  color: var(--el-text-color-regular);
}
.desc-card {
  margin-top: 24px;
}
.desc-title {
  font-weight: 600;
}
.desc-body {
  white-space: pre-wrap;
  color: var(--el-text-color-regular);
  line-height: 1.7;
  margin: 0;
}
</style>
