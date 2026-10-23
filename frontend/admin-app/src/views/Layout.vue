<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import { confirmAction } from '../utils/confirm'
import { visibleMenus } from '../utils/menu'

const auth = useAuthStore()
const router = useRouter()

/**
 * ★ 菜单 = 纯数据（utils/menu.ts）+ 当前权限码。好处有两个：
 *   ① 增删入口只改一处，不会出现「路由加了、菜单忘了」；
 *   ② 显隐规则可以被单测钉住（menu.spec.ts），而模板里的 v-if 链不行。
 * ⚠️ 仍然只是体验：直接敲 URL 会被后端 @PreAuthorize 挡成 403（管理端 403 是常态）。
 */
const menus = computed(() => visibleMenus(auth.perms))

async function onExit() {
  // ★ 同一类事故：旧写法 confirm().catch(() => null) 会让「取消」也退出登录
  const ok = await confirmAction('确定退出管理后台？', { title: '退出登录' })
  if (!ok) return
  auth.logout()
  ElMessage.success('已退出')
  router.push('/login')
}
</script>

<template>
  <el-container class="shell">
    <el-aside width="200px" class="aside">
      <!-- ★ 品牌区与 C 端同款（渐变方块 + 名称）：两个应用看起来要像一家公司的产品 -->
      <div class="brand">
        <span class="brand-mark">M</span>
        <span class="brand-text">MallX 管理后台</span>
      </div>
      <el-menu router :default-active="$route.path" class="menu">
        <!-- ★ 菜单项来自 utils/menu.ts：入口与权限码的对应关系只有一处，
             且被 menu.spec.ts 锁着（写错一个字符 = 入口静默消失） -->
        <el-menu-item v-for="m in menus" :key="m.path" :index="m.path">
          {{ m.label }}
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <span class="who">
          管理员：<b>{{ auth.username || '-' }}</b>
          <!-- ★ 权限码：管理端 token 才有 perms；C 端 token 是空的 -->
          <el-tag size="small" type="info">{{ auth.perms.length }} 项权限</el-tag>
        </span>
        <el-button link @click="onExit">退出</el-button>
      </el-header>

      <el-main class="main">
        <!-- 子路由出口（★ 与 C 端同一套过渡动画名，手感一致） -->
        <router-view v-slot="{ Component }">
          <transition name="brand-fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.shell {
  height: 100vh;
}
.aside {
  background: var(--admin-aside-bg);
  /* ★ 菜单项变多之后，999 高度的窗口放不下：让菜单自己滚，而不是把「退出」顶出视口 */
  display: flex;
  flex-direction: column;
}
.brand {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #fff;
  font-weight: 600;
  letter-spacing: 0.5px;
  background: var(--admin-aside-bg-deep);
}
/* ★ 与 C 端同款品牌方块（CSS 渐变，不引图片资源） */
.brand-mark {
  width: 26px;
  height: 26px;
  border-radius: var(--brand-radius-sm);
  background: var(--brand-gradient);
  color: #fff;
  font-weight: 800;
  font-size: 15px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: none;
}
.brand-text {
  font-size: 14px;
}

/**
 * ★★ 这一版最重要的修复：深色侧栏必须显式给 EP 菜单【文字色】。
 *
 * <p>原代码把 .menu 的背景刷成了深色，却没动 --el-menu-text-color ——
 * EP 的默认值是 #303133（深灰），铺在 #1f2430 上几乎看不见，
 * 菜单等于「隐身」。这是「看着不对劲」的直接来源之一。
 *
 * <p>★ 用 EP 自己的变量改，而不是 :deep 压 .el-menu-item：变量是官方入口，
 * 覆盖的是「这一棵菜单树」，也不会和 EP 的 hover/active 优先级打架。
 */
.menu {
  border-right: none;
  background: var(--admin-aside-bg);
  flex: 1;
  overflow-y: auto;
  --el-menu-bg-color: var(--admin-aside-bg);
  --el-menu-text-color: rgba(255, 255, 255, 0.72);
  --el-menu-hover-text-color: #fff;
  --el-menu-hover-bg-color: rgba(255, 255, 255, 0.06);
  --el-menu-active-color: #fff;
}
/* ★ 选中项：浅色块 + 左侧 3px 指示条（深色侧栏上的通用做法，比只改文字色明确得多）
   ⚠️ 这里的半透明色是【跟着主色走】的 —— 主色换橙后必须同步，否则选中块还是旧的靛蓝。 */
.menu :deep(.el-menu-item.is-active) {
  background: rgba(255, 103, 0, 0.18);
  position: relative;
}
.menu :deep(.el-menu-item.is-active)::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: var(--brand-color-light);
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: #fff;
}
.who {
  font-size: 14px;
  color: var(--el-text-color-regular);
}
.who b {
  color: var(--el-text-color-primary);
}
.who .el-tag {
  margin-left: 10px;
}
.main {
  background: var(--el-fill-color-light);
}
</style>
