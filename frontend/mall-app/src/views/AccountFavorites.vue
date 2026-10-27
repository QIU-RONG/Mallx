<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { favoritePage, favoriteRemove } from '../api'
import ProductThumb from '../components/ProductThumb.vue'
import type { FavoriteVO } from '../types/api'

/** 我的收藏（Day 82）：取消收藏是物理删除，接口幂等 */
const router = useRouter()
const rows = ref<FavoriteVO[]>([])
const total = ref(0)
const current = ref(1)
const size = 12
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const j = await favoritePage(current.value, size)
    rows.value = j.data.records || []
    total.value = j.data.total
  } finally {
    loading.value = false
  }
}

async function remove(productId: number) {
  await favoriteRemove(productId)
  ElMessage.success('已取消收藏')
  if (rows.value.length === 1 && current.value > 1) current.value -= 1
  load()
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="wrap">
    <header class="head">
      <div>
        <h1 class="title">我的收藏</h1>
        <p class="sub">喜欢的商品先收着，降价了再回来看看</p>
      </div>
      <span class="count">{{ total }} 件</span>
    </header>

    <el-empty v-if="!rows.length && !loading" description="还没有收藏任何商品">
      <el-button type="primary" @click="router.push('/')">去逛逛</el-button>
    </el-empty>

    <div v-else class="grid">
      <article
        v-for="f in rows"
        :key="f.productId"
        class="card"
        @click="router.push(`/product/${f.productId}`)"
      >
        <div class="pic">
          <ProductThumb :src="f.mainImage" :name="f.name" :seed="f.productId" />
        </div>
        <div class="name">{{ f.name || '商品已下架' }}</div>
        <div class="row">
          <span v-if="f.minPrice != null" class="price mx-serif">¥{{ Number(f.minPrice).toFixed(2) }}</span>
          <span v-else class="muted">暂无报价</span>
          <button class="remove" type="button" @click.stop="remove(f.productId)">取消收藏</button>
        </div>
      </article>
    </div>

    <el-pagination
      v-model:current-page="current"
      :page-size="size"
      :total="total"
      layout="prev, pager, next"
      style="margin-top: 24px"
      @current-change="load"
    />
  </div>
</template>

<style scoped>
.wrap {
  min-height: 320px;
}
.head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--mx-line);
}
.title {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -0.01em;
}
.sub {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--mx-ink-2);
}
.count {
  font-size: 12px;
  color: var(--mx-ink-3);
}
.grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 20px;
  margin-top: 22px;
}
.card {
  border: 1px solid var(--mx-line);
  border-radius: var(--mx-card-r);
  background: var(--mx-surface);
  padding: 12px;
  cursor: pointer;
  transition:
    border-color 0.18s var(--mx-ease),
    transform 0.18s var(--mx-ease);
}
.card:hover {
  border-color: var(--mx-ink-3);
  transform: translateY(-2px);
}
.pic {
  aspect-ratio: 4 / 3;
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
.row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-top: 8px;
}
.price {
  font-size: 16px;
  color: var(--mx-ink);
}
.muted {
  font-size: 12px;
  color: var(--mx-ink-3);
}
.remove {
  border: none;
  background: transparent;
  padding: 0;
  font-size: 12px;
  color: var(--mx-ink-3);
  cursor: pointer;
}
.remove:hover {
  color: #b3261e;
}
@media (max-width: 900px) {
  .grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
