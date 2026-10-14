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
    <!-- ★ 品牌区：一个 CSS 画的方块图标 + 名称，提供「这是谁家的店」的视觉记忆点 -->
    <div class="brand" @click="router.push('/')">
      <span class="brand-mark">M</span>
      <span class="brand-name">MallX 商城</span>
    </div>

    <!-- ★ :default-active 绑当前路由：写死 '/' 会导致跳到订单页时首页仍高亮 -->
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

    <!-- ★ 配色收敛：这里原本是 type="warning"（琥珀 #e6a23c）。
         加上品牌色、登录蓝、退出红，顶栏一屏蹦出五种颜色，全在喊。
         warning 与主色最冲突（同为暖色系却不同色相），改回 primary link 跟随主题。
         购物车是转化入口，用主色强调是合理的，不再另起一个色。 -->
    <el-badge :value="cartStore.selectedCount" :hidden="!cartStore.selectedCount" class="cart">
      <el-button link type="primary" @click="router.push('/cart')">购物车</el-button>
    </el-badge>
    <template v-if="auth.token">
      <span class="user">{{ auth.nickname }}</span>
      <el-button link @click="logout">退出</el-button>
    </template>
    <template v-else>
      <el-button link type="primary" @click="router.push('/login')">登录</el-button>
    </template>
  </el-header>

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
  display: flex;
  align-items: center;
  gap: 8px;
  background: #fff;
  /* ★ 只留阴影，去掉 1px 边框 —— 两者同时存在是重复的层次表达，会显得脏 */
  box-shadow: var(--brand-shadow);
  height: var(--brand-header-h);
  padding: 0 16px;
  /* ★ 吸顶：页面长的时候顶栏跟着走，不用回到顶部才能换导航 */
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
/* ★ 品牌图标：渐变方块 + 首字母。不引图片资源，改主题色时它跟着变。
   ⚠️ 这里【不再】常驻 box-shadow —— 上一版挂了 hover 阴影（还带彩色），
   静止状态就有一圈发光，是「显脏」的来源之一。 */
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
  color: var(--brand-color-dark);
  letter-spacing: 0.5px;
}
.nav {
  border-bottom: none;
  flex: none;
  margin-left: 12px;
}
/* ★ 菜单选中色【不再】单独覆盖：--el-color-primary 已全局改成品牌色，
   el-menu 的 active-color 默认就取它。少一处重复定义，就少一处将来会漂的地方。 */
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
