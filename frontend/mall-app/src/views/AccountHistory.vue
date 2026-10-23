<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import ProductThumb from '../components/ProductThumb.vue'
import { clearViewHistory, getViewHistory, type ViewedProduct } from '../utils/history'

/**
 * 浏览记录（Day 69）。
 * ★ 数据在 localStorage：换设备/换浏览器不会同步 —— 这是刻意的（见 utils/history.ts 头注释）。
 */
const router = useRouter()
const rows = ref<ViewedProduct[]>([])

function fmtTime(ms: number) {
  const d = new Date(ms)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getMonth() + 1}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function load() {
  rows.value = getViewHistory()
}

async function clear() {
  const ok = await ElMessageBox.confirm('清空后无法恢复，确定？', '清空浏览记录', {
    type: 'warning',
    confirmButtonText: '清空',
    cancelButtonText: '取消',
  })
    .then(() => true)
    .catch(() => false)
  if (!ok) return
  clearViewHistory()
  load()
}

onMounted(load)
</script>

<template>
  <div class="history">
    <header class="head">
      <div>
        <h1 class="title">浏览记录</h1>
        <p class="sub">最近看过的商品，最多保留 20 件；只存在这台设备上</p>
      </div>
      <button v-if="rows.length" class="clear" type="button" @click="clear">清空记录</button>
    </header>

    <el-empty v-if="!rows.length" description="还没有浏览过商品">
      <el-button type="primary" @click="router.push('/')">去逛逛</el-button>
    </el-empty>

    <ul v-else class="list">
      <li v-for="p in rows" :key="p.id" class="item" @click="router.push(`/product/${p.id}`)">
        <div class="pic">
          <ProductThumb :src="p.image" :name="p.name" :seed="p.id" />
        </div>
        <div class="main">
          <div class="name">{{ p.name }}</div>
          <div class="meta">
            <span v-if="p.price != null" class="price mx-serif">¥{{ Number(p.price).toFixed(2) }}</span>
            <span class="time">{{ fmtTime(p.at) }}</span>
          </div>
        </div>
        <span class="go">查看 →</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.history {
  min-height: 320px;
}
.head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
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
.clear {
  border: none;
  background: transparent;
  padding: 0;
  font-size: 12px;
  color: var(--mx-ink-3);
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 4px;
}
.clear:hover {
  color: var(--mx-ink);
}
.list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 4px;
  border-bottom: 1px solid var(--mx-line-soft);
  cursor: pointer;
  transition: background 0.18s var(--mx-ease);
}
.item:hover {
  background: var(--mx-line-soft);
}
.pic {
  width: 64px;
  height: 64px;
  border-radius: var(--mx-media-r);
  overflow: hidden;
  border: 1px solid var(--mx-line);
  flex: none;
}
.main {
  flex: 1;
  min-width: 0;
}
.name {
  font-size: 14px;
  font-weight: 600;
  color: var(--mx-ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.meta {
  display: flex;
  align-items: baseline;
  gap: 14px;
  margin-top: 6px;
}
.price {
  font-size: 15px;
  color: var(--mx-ink);
}
.time {
  font-size: 12px;
  color: var(--mx-ink-3);
}
.go {
  flex: none;
  font-size: 12px;
  color: var(--mx-ink-3);
}
</style>
