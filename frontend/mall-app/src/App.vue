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
    <div class="brand" @click="router.push('/')">MallX 商城</div>
    <el-menu mode="horizontal" :ellipsis="false" class="nav" :default-active="'/'" router>
      <el-menu-item index="/">首页</el-menu-item>
      <el-menu-item index="/coupons">优惠券</el-menu-item>
      <el-menu-item index="/orders">我的订单</el-menu-item>
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
  <router-view />
</template>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  height: 60px;
  padding: 0 16px;
}
.brand {
  font-size: 20px;
  font-weight: 700;
  color: #409eff;
  cursor: pointer;
}
.nav {
  border-bottom: none;
  flex: none;
}
.spacer {
  flex: 1;
}
.user {
  margin-right: 12px;
  color: #606266;
}
.cart {
  margin-right: 12px;
}
</style>
