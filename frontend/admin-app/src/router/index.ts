import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

/**
 * 管理端路由。
 * ★ 与 C 端不同：管理端【所有】页面都要登录 —— 没有「公开页」这回事
 *   （后端 /api/admin/** 不在白名单里，匿名必 401）。
 */
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: () => import('../views/Login.vue') },
    {
      path: '/',
      component: () => import('../views/Layout.vue'),
      redirect: '/dashboard',
      children: [
        { path: 'dashboard', component: () => import('../views/Dashboard.vue') },
        { path: 'products', component: () => import('../views/ProductList.vue') },
        { path: 'orders', component: () => import('../views/OrderList.vue') },
        { path: 'orders/:id', component: () => import('../views/OrderDetail.vue') },
        { path: 'refunds', component: () => import('../views/RefundList.vue') },
      ],
    },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  auth.restore()
  if (to.path !== '/login' && !auth.isLogin) {
    return '/login'
  }
  if (to.path === '/login' && auth.isLogin) {
    return '/'
  }
  return true
})

export default router
