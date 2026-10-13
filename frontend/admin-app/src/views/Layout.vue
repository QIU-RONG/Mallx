<script setup lang="ts">
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

async function onExit() {
  await ElMessageBox.confirm('确定退出管理后台？', '提示', { type: 'warning' }).catch(() => null)
  auth.logout()
  ElMessage.success('已退出')
  router.push('/login')
}
</script>

<template>
  <el-container class="shell">
    <el-aside width="200px" class="aside">
      <div class="brand">MallX 管理后台</div>
      <el-menu router :default-active="$route.path" class="menu">
        <el-menu-item index="/dashboard">概览</el-menu-item>
        <el-menu-item index="/products">商品管理</el-menu-item>
        <el-menu-item index="/orders">订单管理</el-menu-item>
        <!-- ★ 售后入口按权限码显隐：没有 refund:list 的人连菜单都看不到
             （只是体验 —— 直接敲 URL 也会被后端 @PreAuthorize 挡成 403） -->
        <el-menu-item v-if="auth.hasPerm('refund:list')" index="/refunds">售后管理</el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <span class="who">
          管理员：<b>{{ auth.username || '-' }}</b>
          <!-- ★ 权限码：管理端 token 才有 perms；C 端 token 是空的 -->
          <el-tag size="small" type="info">{{ auth.perms.length }} 项权限</el-tag>
        </span>
        <el-button link type="danger" @click="onExit">退出</el-button>
      </el-header>

      <el-main class="main">
        <!-- 子路由出口 -->
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.shell {
  height: 100vh;
}
.aside {
  background: #1f2430;
}
.brand {
  height: 60px;
  line-height: 60px;
  text-align: center;
  color: #fff;
  font-weight: 600;
  letter-spacing: 1px;
  background: #171b24;
}
.menu {
  border-right: none;
  background: #1f2430;
}
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #ebeef5;
  background: #fff;
}
.who {
  font-size: 14px;
  color: #606266;
}
.who b {
  color: #303133;
}
.who .el-tag {
  margin-left: 10px;
}
.main {
  background: #f5f7fa;
}
</style>
