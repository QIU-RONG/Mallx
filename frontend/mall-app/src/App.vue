<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'
import { useCartStore } from './stores/cart'
import { useCatalogStore } from './stores/catalog'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const cartStore = useCartStore()
const catalog = useCatalogStore()

/** 搜索框内容 —— 与 URL 单向同步：只有「点搜索 / 回车」才写 query */
const kw = ref('')

onMounted(() => {
  if (auth.token) cartStore.refresh()
  // ★ 顶栏的品类导航要用分类树；store 里做了「只请求一次」，列表页共用同一份
  catalog.ensure()
  kw.value = (route.query.kw as string) || ''
})

function logout() {
  auth.logout()
  cartStore.clear()
  router.push('/login')
}

/**
 * ★ 搜索 / 选品类都走「跳回首页 + 带 query」，而不是去改列表页的内部状态。
 *
 * <p><b>为什么</b>：顶栏是**全局**组件，它并不知道当前在不在首页，
 * 更不该去操作别人的状态。统一走路由 ⇒ 列表页只认 query，
 * 「一个入口、一条数据流」，不会出现「顶栏变了、页面没动」这种灵异现象。
 *
 * <p>顺带的好处：URL 变成可分享、可前进后退的（`/?categoryId=2&kw=手机`）——
 * 这是商城该有的行为。
 */
function goHome(query: Record<string, string | undefined> = {}) {
  router.push({ path: '/', query })
}

function doSearch() {
  goHome({ kw: kw.value.trim() || undefined })
}
</script>

<template>
  <!-- ═══════════ 顶栏（单行 · 吸顶）═══════════
       Day 57：把原来的「浅灰工具条 + 主导航」两层合并成一层。
       编辑风需要一个安静、只有一条发丝线的顶栏；工具条上的入口收进右侧文字链接。 -->
  <header class="topbar">
    <div class="topbar-inner">
      <div class="brand" @click="goHome()">
        <span class="brand-mark">M</span>
        <span class="brand-word">MallX</span>
        <span class="brand-sub">商城</span>
      </div>

      <nav class="cats">
        <a
          class="cat"
          :class="{ active: route.path === '/' && !route.query.categoryId }"
          @click="goHome()"
        >
          全部
        </a>
        <a
          v-for="c in catalog.tree"
          :key="c.id"
          class="cat"
          :class="{ active: String(route.query.categoryId) === String(c.id) }"
          @click="goHome({ categoryId: String(c.id) })"
        >
          {{ c.name }}
        </a>
      </nav>

      <div class="search">
        <el-input
          v-model="kw"
          placeholder="搜索商品"
          clearable
          @keyup.enter="doSearch"
          @clear="doSearch"
        >
          <template #prefix>
            <svg
              viewBox="0 0 24 24"
              width="15"
              height="15"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
            >
              <circle cx="11" cy="11" r="7" />
              <path d="m20 20-3.2-3.2" />
            </svg>
          </template>
        </el-input>
        <button class="search-go" type="button" @click="doSearch">搜索</button>
      </div>

      <div class="actions">
        <template v-if="auth.token">
          <a class="a-link" @click="router.push('/orders')">订单</a>
          <a class="a-link" @click="router.push('/refunds')">售后</a>
          <a class="a-link" @click="router.push('/coupons')">券</a>
          <a class="a-link" @click="logout">退出</a>
        </template>
        <template v-else>
          <a class="a-link" @click="router.push('/login')">登录</a>
          <a class="a-link a-link--strong" @click="router.push('/login')">注册</a>
        </template>

        <el-badge :value="cartStore.selectedCount" :hidden="!cartStore.selectedCount">
          <button class="cart-entry" type="button" @click="router.push('/cart')">
            <svg
              class="cart-icon"
              viewBox="0 0 24 24"
              width="16"
              height="16"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <circle cx="9" cy="20" r="1.2" />
              <circle cx="18" cy="20" r="1.2" />
              <path d="M2.5 3.5h2.6l2.4 12a1.4 1.4 0 0 0 1.4 1.1h8.4a1.4 1.4 0 0 0 1.4-1.1L20 7.5H6.2" />
            </svg>
            <span>购物车</span>
          </button>
        </el-badge>
      </div>
    </div>
  </header>

  <!-- ★ 路由切换动画：<router-view v-slot> 拿当前组件，外包 transition。
       mode="out-in" 让旧的先走再进新的，避免两页同时在场时布局跳动。 -->
  <router-view v-slot="{ Component }">
    <transition name="brand-fade" mode="out-in">
      <component :is="Component" />
    </transition>
  </router-view>
</template>

<style scoped>
.topbar {
  position: sticky;
  top: 0;
  z-index: 100;
  background: color-mix(in srgb, var(--mx-paper) 92%, transparent);
  backdrop-filter: saturate(180%) blur(10px);
  border-bottom: 1px solid var(--mx-line);
}
.topbar-inner {
  max-width: 1200px;
  margin: 0 auto;
  height: var(--mx-topbar-h);
  padding: 0 20px;
  display: flex;
  align-items: center;
  gap: 28px;
}

/* ───── 品牌 ───── */
.brand {
  display: flex;
  align-items: baseline;
  gap: 8px;
  cursor: pointer;
  user-select: none;
  flex: none;
}
.brand-mark {
  width: 26px;
  height: 26px;
  border-radius: 6px;
  background: var(--mx-ink);
  color: #fff;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 16px;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  align-self: center;
}
.brand-word {
  font-family: Georgia, 'Times New Roman', 'Songti SC', serif;
  font-size: 20px;
  font-weight: 600;
  letter-spacing: 0.01em;
  color: var(--mx-ink);
}
.brand-sub {
  font-size: 12px;
  letter-spacing: 0.18em;
  color: var(--mx-ink-3);
}

/* ───── 品类 ───── */
.cats {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 22px;
  overflow-x: auto;
  scrollbar-width: none;
}
.cats::-webkit-scrollbar {
  display: none;
}
.cat {
  position: relative;
  flex: none;
  padding: 6px 0;
  font-size: 13px;
  letter-spacing: 0.02em;
  color: var(--mx-ink-2);
  cursor: pointer;
  white-space: nowrap;
  transition: color 0.18s var(--mx-ease);
}
.cat:hover {
  color: var(--mx-ink);
}
/* ★ 编辑风的选中态：不描底色，只在字下方画 2px 橙线 */
.cat.active {
  color: var(--mx-ink);
  font-weight: 600;
}
.cat.active::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: -1px;
  height: 2px;
  background: var(--mx-accent);
}

/* ───── 搜索 ───── */
.search {
  flex: none;
  display: flex;
  align-items: center;
  border: 1px solid var(--mx-line);
  border-radius: var(--mx-btn-r);
  background: var(--mx-surface);
  overflow: hidden;
  transition: border-color 0.18s var(--mx-ease);
}
.search:focus-within {
  border-color: var(--mx-ink-3);
}
.search :deep(.el-input__wrapper) {
  box-shadow: none !important;
  background: transparent;
  padding: 2px 10px;
}
.search :deep(.el-input__inner) {
  font-size: 13px;
}
.search :deep(.el-input__prefix) {
  color: var(--mx-ink-3);
}
.search-go {
  height: 34px;
  padding: 0 14px;
  border: none;
  border-left: 1px solid var(--mx-line);
  background: transparent;
  color: var(--mx-ink);
  font-size: 13px;
  /* ★ 必须 nowrap：搜索框只有 230px 时按钮会被挤成「搜 / 索」两行（实测踩到） */
  white-space: nowrap;
  flex: none;
  cursor: pointer;
  transition: background 0.18s var(--mx-ease);
}
.search-go:hover {
  background: var(--mx-line-soft);
}

/* ───── 右侧操作 ───── */
.actions {
  flex: none;
  display: flex;
  align-items: center;
  gap: 16px;
}
.a-link {
  font-size: 12px;
  color: var(--mx-ink-2);
  cursor: pointer;
  white-space: nowrap;
  transition: color 0.18s var(--mx-ease);
}
.a-link:hover {
  color: var(--mx-ink);
}
.a-link--strong {
  color: var(--mx-ink);
  font-weight: 600;
}
.cart-entry {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 14px;
  border: 1px solid var(--mx-line);
  border-radius: 999px;
  background: var(--mx-surface);
  color: var(--mx-ink);
  font-size: 12px;
  cursor: pointer;
  transition:
    border-color 0.18s var(--mx-ease),
    background 0.18s var(--mx-ease);
}
.cart-entry:hover {
  border-color: var(--mx-ink-3);
  background: var(--mx-line-soft);
}
.cart-icon {
  flex: none;
}

@media (max-width: 1080px) {
  .topbar-inner {
    gap: 18px;
  }
  .cats {
    gap: 16px;
  }
  .search {
    width: 190px;
  }
}
@media (max-width: 860px) {
  .brand-sub {
    display: none;
  }
  .search {
    width: 150px;
  }
  .search-go {
    display: none;
  }
}
</style>
