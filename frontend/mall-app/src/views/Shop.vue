<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { pageProducts, shopDetail } from '../api'
import ProductThumb from '../components/ProductThumb.vue'
import type { ProductVO, ShopVO } from '../types/api'

/**
 * 店铺主页（Day 81）——商品详情里的店铺胶囊点进来。
 *
 * ★ 只展示该店商品；店铺信息走公开接口，停用店铺 404（页面显示空态）。
 * ★ 分类筛选刻意不做：店铺主页的场景是「逛这家店」，不是比价。
 */
const route = useRoute()
const router = useRouter()

const shop = ref<ShopVO | null>(null)
const rows = ref<ProductVO[]>([])
const total = ref(0)
const current = ref(1)
const size = 12
const loading = ref(false)

async function loadProducts() {
  loading.value = true
  try {
    const j = await pageProducts({
      current: current.value,
      size,
      shopId: Number(route.params.id),
    })
    rows.value = j.data.records || []
    total.value = j.data.total
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    shop.value = (await shopDetail(route.params.id as string)).data
  } catch {
    shop.value = null
  }
  loadProducts()
})
</script>

<template>
  <div v-loading="loading" class="wrap">
    <header class="shop-head">
      <p class="eyebrow">MALLX SHOP</p>
      <h1 class="title">{{ shop?.name || '店铺' }}</h1>
      <p v-if="shop?.description" class="desc">{{ shop.description }}</p>
      <p class="count">共 {{ total }} 件商品</p>
    </header>

    <el-empty v-if="!rows.length && !loading" description="这家店还没有上架商品" />

    <div v-else class="grid">
      <article
        v-for="p in rows"
        :key="p.id"
        class="card"
        @click="router.push(`/product/${p.id}`)"
      >
        <div class="pic">
          <ProductThumb :src="p.mainImage" :name="p.name" :seed="p.id" />
        </div>
        <div class="name">{{ p.name }}</div>
        <div class="bottom">
          <span v-if="p.minPrice != null" class="price mx-serif">
            ¥{{ Number(p.minPrice).toFixed(2) }}
          </span>
          <span v-if="p.brandName" class="brand">{{ p.brandName }}</span>
        </div>
      </article>
    </div>

    <el-pagination
      v-model:current-page="current"
      :page-size="size"
      :total="total"
      layout="prev, pager, next"
      style="margin-top: 28px"
      @current-change="loadProducts"
    />
  </div>
</template>

<style scoped>
.wrap {
  max-width: 1320px;
  margin: 0 auto;
  padding: 40px 24px 80px;
  min-height: 320px;
}
.shop-head {
  padding-bottom: 24px;
  border-bottom: 1px solid var(--mx-line);
}
.eyebrow {
  margin: 0;
  font-size: 11px;
  letter-spacing: 0.22em;
  color: var(--mx-ink-3);
}
.title {
  margin: 10px 0 0;
  font-size: 30px;
  font-weight: 600;
  letter-spacing: -0.01em;
}
.desc {
  margin: 10px 0 0;
  font-size: 14px;
  color: var(--mx-ink-2);
}
.count {
  margin: 12px 0 0;
  font-size: 12px;
  color: var(--mx-ink-3);
}
.grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 24px;
  margin-top: 28px;
}
.card {
  cursor: pointer;
  border: 1px solid var(--mx-line);
  border-radius: var(--mx-card-r);
  background: var(--mx-surface);
  padding: 12px;
  transition:
    border-color 0.18s var(--mx-ease),
    transform 0.18s var(--mx-ease);
}
.card:hover {
  border-color: var(--mx-ink-3);
  transform: translateY(-2px);
}
.pic {
  aspect-ratio: 4 / 5;
  border-radius: var(--mx-media-r);
  overflow: hidden;
}
.name {
  margin-top: 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--mx-ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bottom {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-top: 8px;
}
.price {
  font-size: 16px;
  color: var(--mx-ink);
}
.brand {
  font-size: 12px;
  color: var(--mx-ink-3);
}
@media (max-width: 1000px) {
  .grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
