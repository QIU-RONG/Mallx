<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { myReviews } from '../api'
import ProductThumb from '../components/ProductThumb.vue'
import type { ReviewVO } from '../types/api'

/**
 * 我的评价（Day 61）。
 * ★ 后端 GET /api/reviews/my 的归属条件写在 SQL 里，前端不传 userId。
 */
const router = useRouter()
const rows = ref<ReviewVO[]>([])
const total = ref(0)
const page = ref(1)
const size = 10
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const j = await myReviews(page.value, size)
    rows.value = j.data.records
    total.value = j.data.total
  } finally {
    loading.value = false
  }
}

function fmtTime(s?: string) {
  return s ? s.replace('T', ' ').slice(0, 16) : ''
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="wrap">
    <h3>我的评价</h3>

    <el-empty v-if="!rows.length && !loading" description="还没有评价过商品">
      <el-button type="primary" @click="router.push('/account/orders')">去订单里评价</el-button>
    </el-empty>

    <article v-for="r in rows" :key="r.id" class="review">
      <div class="pic">
        <router-link :to="`/product/${r.productId}`">
          <ProductThumb :src="r.image" :name="r.productName" :seed="r.productId" />
        </router-link>
      </div>
      <div class="main">
        <div class="top">
          <router-link class="name" :to="`/product/${r.productId}`">{{ r.productName }}</router-link>
          <span class="sku">{{ r.skuName }}</span>
          <el-rate :model-value="r.rating" disabled size="small" />
          <span class="time">{{ fmtTime(r.createdAt) }}</span>
        </div>
        <p class="content">{{ r.content || '（未填写文字）' }}</p>
      </div>
    </article>

    <el-pagination
      v-model:current-page="page"
      :page-size="size"
      :total="total"
      layout="total, prev, pager, next"
      style="margin-top: 24px"
      @current-change="load"
    />
  </div>
</template>

<style scoped>
.wrap {
  min-height: 260px;
}
.review {
  display: flex;
  gap: 14px;
  padding: 18px 0;
  border-bottom: 1px solid var(--mx-line-soft);
}
.pic {
  width: 56px;
  height: 56px;
  border-radius: var(--mx-media-r);
  overflow: hidden;
  border: 1px solid var(--mx-line);
  flex: none;
  background: var(--mx-line-soft);
}
.pic :deep(.thumb) {
  width: 100%;
  height: 100%;
}
.main {
  flex: 1;
  min-width: 0;
}
.top {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.name {
  font-size: 14px;
  font-weight: 600;
  color: var(--mx-ink);
  text-decoration: none;
}
.name:hover {
  text-decoration: underline;
}
.sku {
  font-size: 12px;
  color: var(--mx-ink-3);
}
.time {
  margin-left: auto;
  font-size: 12px;
  color: var(--mx-ink-3);
}
.content {
  margin: 8px 0 0;
  font-size: 14px;
  line-height: 1.7;
  color: var(--mx-ink-2);
  white-space: pre-wrap;
}
</style>
