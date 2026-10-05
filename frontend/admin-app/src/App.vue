<script setup lang="ts">
// 管理端外壳：只负责挂载路由。
// 侧边栏 / 顶栏在 Layout.vue 里（未登录时走 Login.vue，不套壳）。
</script>

<template>
  <router-view />
</template>
