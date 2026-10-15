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
  <!-- ═══════════ 第一层：工具条 ═══════════
       仿华为 / 小米：最上面一条浅灰窄条，放「不常点但偶尔要用」的功能入口
       （订单 / 售后 / 券 / 登录）。把它和主导航分开，主导航才装得下品类。 -->
  <div class="utility">
    <div class="utility-inner">
      <span class="welcome">
        {{ auth.token ? `Hi，${auth.nickname}` : '欢迎来到 MallX 商城' }}
      </span>
      <div class="spacer" />
      <template v-if="auth.token">
        <a class="u-link" @click="router.push('/orders')">我的订单</a>
        <span class="u-sep" />
        <a class="u-link" @click="router.push('/refunds')">我的售后</a>
        <span class="u-sep" />
        <a class="u-link" @click="router.push('/coupons')">优惠券</a>
        <span class="u-sep" />
        <a class="u-link" @click="logout">退出</a>
      </template>
      <template v-else>
        <a class="u-link" @click="router.push('/login')">登录</a>
        <span class="u-sep" />
        <a class="u-link" @click="router.push('/login')">注册</a>
      </template>
    </div>
  </div>

  <!-- ═══════════ 第二层：主导航（吸顶）═══════════
       logo | 品类导航 | 搜索框 | 购物车 —— 国内商城顶栏的固定排布。
       品类导航直接吃真实分类树，点谁就带着 categoryId 回首页。 -->
  <div class="mainnav">
    <div class="mainnav-inner">
      <div class="brand" @click="goHome()">
        <span class="brand-mark">M</span>
        <span class="brand-name">MallX 商城</span>
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

      <!-- ★ 搜索框放在主导航里、且是常驻可见的 ——
           商城的搜索永远在最显眼处，藏进菜单等于没有。 -->
      <div class="search">
        <el-input
          v-model="kw"
          placeholder="搜索商品名 / 副标题"
          clearable
          @keyup.enter="doSearch"
          @clear="doSearch"
        />
        <el-button type="primary" class="search-btn" @click="doSearch">搜索</el-button>
      </div>

      <el-badge
        :value="cartStore.selectedCount"
        :hidden="!cartStore.selectedCount"
        class="cart-badge"
      >
        <button class="cart-entry" type="button" @click="router.push('/cart')">
          <!-- ★ 内联 SVG 而不是 emoji：emoji 在各系统的字形/基线都不同，看着不专业 -->
          <svg
            class="cart-icon"
            viewBox="0 0 24 24"
            width="17"
            height="17"
            fill="none"
            stroke="currentColor"
            stroke-width="1.7"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <circle cx="9" cy="20" r="1.3" />
            <circle cx="18" cy="20" r="1.3" />
            <path d="M2.5 3.5h2.6l2.4 12a1.4 1.4 0 0 0 1.4 1.1h8.4a1.4 1.4 0 0 0 1.4-1.1L20 7.5H6.2" />
          </svg>
          <span>购物车</span>
        </button>
      </el-badge>
    </div>
  </div>

  <!-- ★ 路由切换动画：<router-view v-slot> 拿当前组件，外包 transition。
       mode="out-in" 让旧的先走再进新的，避免两页同时在场时布局跳动。 -->
  <router-view v-slot="{ Component }">
    <transition name="brand-fade" mode="out-in">
      <component :is="Component" />
    </transition>
  </router-view>
</template>

<style scoped>
/* ─────────── 第一层：工具条 ─────────── */
.utility {
  height: var(--brand-utility-h);
  /* ★ 浅灰而不是纯白：与下面的白色主导航形成分层，
     否则两条白栏叠在一起会糊成一块。 */
  background: var(--el-fill-color-light);
  border-bottom: 1px solid var(--el-border-color-lighter);
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.utility-inner {
  max-width: 1200px;
  margin: 0 auto;
  height: 100%;
  padding: 0 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.u-link {
  cursor: pointer;
}
.u-link:hover {
  color: var(--brand-color);
}
.u-sep {
  width: 1px;
  height: 11px;
  background: var(--el-border-color);
}
.spacer {
  flex: 1;
}

/* ─────────── 第二层：主导航 ─────────── */
.mainnav {
  background: #fff;
  height: var(--brand-header-h);
  box-shadow: var(--brand-shadow);
  /* ★ 吸顶只加在主导航上：工具条随页面滚走，滚动后正好只留主导航，
     相当于「自动收纳」——不用写 JS 监听滚动高度。 */
  position: sticky;
  top: 0;
  z-index: 100;
}
.mainnav-inner {
  max-width: 1200px;
  margin: 0 auto;
  height: 100%;
  padding: 0 16px;
  display: flex;
  align-items: center;
  gap: 20px;
}
.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
  flex: none;
}
.brand-mark {
  width: 30px;
  height: 30px;
  border-radius: var(--brand-radius-sm);
  background: var(--brand-gradient);
  color: #fff;
  font-weight: 800;
  font-size: 17px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.brand-name {
  font-size: 19px;
  font-weight: 700;
  color: var(--brand-color);
  letter-spacing: 0.5px;
  white-space: nowrap;
}

/* ───── 品类导航 ─────
   ★ flex:1 + overflow-x:auto：品类多到装不下时横向滚动，
   而不是把搜索框挤出屏幕（窄屏上这一点很关键）。
   滚动条隐藏 —— 一条横条出现在顶栏里非常难看。 */
.cats {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 2px;
  overflow-x: auto;
  scrollbar-width: none;
  -ms-overflow-style: none;
}
.cats::-webkit-scrollbar {
  display: none;
}
.cat {
  flex: none;
  padding: 6px 10px;
  font-size: 14px;
  color: var(--el-text-color-regular);
  cursor: pointer;
  border-radius: var(--brand-radius-sm);
  white-space: nowrap;
  transition:
    color 0.15s ease,
    background 0.15s ease;
}
.cat:hover {
  color: var(--brand-color);
}
/* ★ 选中态用「主色文字 + 浅底」，而不是下划线：
   顶栏在两层结构里已经很满，再画线会更碎。 */
.cat.active {
  color: var(--brand-color);
  background: var(--el-color-primary-light-9);
  font-weight: 600;
}

/* ───── 搜索框 ───── */
.search {
  flex: none;
  width: 230px;
  display: flex;
  gap: 6px;
}
.search-btn {
  flex: none;
}

/* ───── 购物车 ───── */
.cart-badge {
  flex: none;
}
.cart-entry {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 12px;
  border: 1px solid var(--el-border-color);
  border-radius: var(--brand-radius-sm);
  background: #fff;
  color: var(--el-text-color-regular);
  font-size: 13px;
  cursor: pointer;
  transition:
    color 0.15s ease,
    border-color 0.15s ease;
}
.cart-entry:hover {
  color: var(--brand-color);
  border-color: var(--brand-color);
}
.cart-icon {
  flex: none;
}

/* ───── 窄屏：优先保搜索和购物车，品类让位 ───── */
@media (max-width: 980px) {
  .search {
    width: 160px;
  }
  .brand-name {
    display: none;
  }
  .mainnav-inner {
    gap: 12px;
  }
}
</style>
