import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('../views/Login.vue') },
    { path: '/', name: 'home', component: () => import('../views/ProductList.vue') },
    { path: '/product/:id', name: 'product-detail', component: () => import('../views/ProductDetail.vue') },
    // FE2 预留：购物车 / 我的订单 / 我的优惠券（届时统一加登录守卫）
  ],
})

// 路由守卫骨架（FE1 无强制登录页；FE2 的 cart/order 路由在此加 auth 校验）
router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.token) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  return true
})

export default router
