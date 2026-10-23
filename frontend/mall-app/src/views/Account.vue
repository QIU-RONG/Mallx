<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import { useCartStore } from '../stores/cart'

/**
 * 个人中心外壳（Day 58）。
 *
 * <p>★ 为什么是「左侧导航 + 子路由」而不是一个带标签页的大页面：
 * 订单 / 售后 / 券这三块已经有页面，把它们作为子路由<b>复用组件</b>，
 * 数据与交互只有一份；个人中心只负责「把它们收进同一个入口」。
 *
 * <p>⚠️ 左侧导航的显隐【只按登录态】，不按权限码 —— C 端 token 没有 perms，
 * 所有登录用户都应该看到自己那几块。
 */
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const cartStore = useCartStore()

const initial = computed(() => (auth.nickname || auth.username || 'M').trim().charAt(0).toUpperCase())

const menus = [
  { to: '/account/overview', label: '概览' },
  { to: '/account/orders', label: '我的订单' },
  { to: '/account/refunds', label: '我的售后' },
  { to: '/account/coupons', label: '优惠券' },
  { to: '/account/reviews', label: '我的评价' },
  { to: '/account/addresses', label: '收货地址' },
  { to: '/account/profile', label: '资料设置' },
]

function onLogout() {
  auth.logout()
  cartStore.clear()
  ElMessage.success('已退出')
  router.push('/')
}
</script>

<template>
  <div class="account">
    <aside class="side">
      <div class="who">
        <div class="avatar">{{ initial }}</div>
        <div class="who-meta">
          <div class="nick">{{ auth.nickname || auth.username }}</div>
          <div class="uname">@{{ auth.username }}</div>
        </div>
      </div>

      <nav class="nav">
        <router-link
          v-for="m in menus"
          :key="m.to"
          :to="m.to"
          class="nav-item"
          :class="{ active: route.path === m.to }"
        >
          {{ m.label }}
        </router-link>
      </nav>

      <button class="logout" type="button" @click="onLogout">退出登录</button>
    </aside>

    <section class="content">
      <router-view v-slot="{ Component }">
        <transition name="brand-fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </section>
  </div>
</template>

<style scoped>
.account {
  max-width: 1200px;
  margin: 0 auto;
  padding: 32px 20px 80px;
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 40px;
  align-items: start;
}

/* ───── 左栏 ───── */
.side {
  background: var(--mx-surface);
  border: 1px solid var(--mx-line);
  border-radius: var(--mx-card-r);
  padding: 24px 18px;
  position: sticky;
  top: calc(var(--mx-topbar-h) + 24px);
}
.who {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--mx-line-soft);
}
.avatar {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: var(--mx-ink);
  color: #fff;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: none;
}
.who-meta {
  min-width: 0;
}
.nick {
  font-size: 15px;
  font-weight: 600;
  color: var(--mx-ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.uname {
  margin-top: 2px;
  font-size: 12px;
  color: var(--mx-ink-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.nav {
  display: flex;
  flex-direction: column;
  margin-top: 14px;
}
.nav-item {
  position: relative;
  padding: 11px 12px;
  border-radius: 6px;
  font-size: 13px;
  color: var(--mx-ink-2);
  text-decoration: none;
  transition:
    color 0.18s var(--mx-ease),
    background 0.18s var(--mx-ease);
}
.nav-item:hover {
  color: var(--mx-ink);
  background: var(--mx-line-soft);
}
/* ★ 选中态与顶栏同一套语言：墨色字 + 左侧 2px 橙条 */
.nav-item.active {
  color: var(--mx-ink);
  font-weight: 600;
  background: var(--mx-line-soft);
}
.nav-item.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 2px;
  background: var(--mx-accent);
}
.logout {
  margin-top: 18px;
  padding: 10px 12px;
  border: none;
  border-top: 1px solid var(--mx-line-soft);
  background: transparent;
  color: var(--mx-ink-3);
  font-size: 12px;
  text-align: left;
  cursor: pointer;
  width: 100%;
}
.logout:hover {
  color: var(--mx-ink);
}

.content {
  min-width: 0;
}

/**
 * ★ 订单 / 售后 / 券三个子路由复用的是【独立页面】组件，它们自带
 * `max-width:1200` 与 20px 内边距 —— 放进个人中心会变成「页面里的页面」，
 * 右侧多出一圈空白、标题字号也与概览页不一致。
 * 这里只中和布局（宽度/内边距）与标题，不动它们内部任何业务样式。
 */
.content :deep(.wrap) {
  max-width: none;
  padding: 0;
  min-height: 0;
}
.content :deep(.wrap > h3) {
  margin: 0 0 20px;
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--mx-ink);
}

@media (max-width: 900px) {
  .account {
    grid-template-columns: 1fr;
    gap: 20px;
    padding-top: 20px;
  }
  .side {
    position: static;
    padding: 16px;
  }
  .who {
    padding-bottom: 12px;
  }
  .nav {
    flex-direction: row;
    overflow-x: auto;
    gap: 4px;
    margin-top: 10px;
  }
  .nav-item {
    white-space: nowrap;
    padding: 8px 10px;
  }
  .nav-item.active::before {
    left: 10px;
    right: 10px;
    top: auto;
    bottom: 0;
    width: auto;
    height: 2px;
  }
  .logout {
    display: none;
  }
}
</style>
