<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'
import { useCartStore } from './stores/cart'

const router = useRouter()
const auth = useAuthStore()
const cartStore = useCartStore()

onMounted(() => {
  if (auth.token) cartStore.refresh()
})

function logout() {
  auth.logout()
  cartStore.clear()
  router.push('/login')
}
</script>

<template>
  <el-header class="topbar">
    <!-- ★ 品牌区：一个 CSS 画的方块图标 + 名称。之前只有一个纯文字 div，
         整个应用没有任何「这是谁家的店」的视觉记忆点。 -->
    <div class="brand" @click="router.push('/')">
      <span class="brand-mark">M</span>
      <span class="brand-name">MallX 商城</span>
    </div>

    <!-- ★ :default-active 绑当前路由：原来写死 '/'，跳到订单页时首页仍高亮 -->
    <el-menu
      mode="horizontal"
      :ellipsis="false"
      class="nav"
      :default-active="router.currentRoute.value.path"
      router
    >
      <el-menu-item index="/">首页</el-menu-item>
      <el-menu-item index="/coupons">优惠券</el-menu-item>
      <el-menu-item index="/orders">我的订单</el-menu-item>
      <el-menu-item index="/refunds">我的售后</el-menu-item>
    </el-menu>

    <div class="spacer" />
    <el-badge :value="cartStore.selectedCount" :hidden="!cartStore.selectedCount" class="cart">
      <el-button link type="warning" @click="router.push('/cart')">购物车</el-button>
    </el-badge>
    <template v-if="auth.token">
      <span class="user">{{ auth.nickname }}</span>
      <el-button link type="danger" @click="logout">退出</el-button>
    </template>
    <template v-else>
      <el-button link type="primary" @click="router.push('/login')">登录</el-button>
    </template>
  </el-header>

  <!-- ★ 路由切换动画：<router-view v-slot> 拿当前组件，外包 transition。
       名字对应 theme.css 里的 .brand-fade-系列。mode="out-in" 让旧的先走再进新的，
       避免两页同时在场时布局跳动。 -->
  <router-view v-slot="{ Component }">
    <transition name="brand-fade" mode="out-in">
      <component :is="Component" />
    </transition>
  </router-view>
</template>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #fff;
  border-bottom: 1px solid var(--el-border-color-lighter);
  /* ★ 贴一点阴影，让顶栏从白页面上「浮」起来 —— 之前是一条 1px 线，层次是平的 */
  box-shadow: var(--brand-shadow);
  height: var(--brand-header-h);
  padding: 0 16px;
  /* ★ 吸顶：页面长的时候顶栏跟着走，不用回顶部才能换导航 */
  position: sticky;
  top: 0;
  z-index: 100;
}
.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
}
/* ★ 品牌图标：渐变方块 + 首字母。不引图片资源，改主题色时它跟着变 */
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
  box-shadow: var(--brand-shadow-hover);
}
.brand-name {
  font-size: 19px;
  font-weight: 700;
  color: var(--brand-color-dark);
  letter-spacing: 0.5px;
}
.nav {
  border-bottom: none;
  flex: none;
  margin-left: 12px;
}
/* ★ 菜单选中色也走品牌色（EP 默认是蓝的，和橙色品牌打架） */
.nav :deep(.el-menu-item.is-active) {
  color: var(--brand-color);
  border-bottom-color: var(--brand-color);
}
.spacer {
  flex: 1;
}
.user {
  margin-right: 12px;
  color: var(--el-text-color-regular);
}
.cart {
  margin-right: 12px;
}
</style>
