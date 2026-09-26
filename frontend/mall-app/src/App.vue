<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'

const router = useRouter()
const auth = useAuthStore()

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <el-header class="topbar">
    <div class="brand" @click="router.push('/')">MallX 商城</div>
    <div class="spacer" />
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
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  height: 60px;
}
.brand {
  font-size: 20px;
  font-weight: 700;
  color: #409eff;
  cursor: pointer;
}
.spacer {
  flex: 1;
}
.user {
  margin-right: 12px;
  color: #606266;
}
</style>
