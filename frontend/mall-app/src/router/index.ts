import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('../views/Login.vue') },
    // Day 52：注册页。★ 刻意【不加】requiresAuth —— 走到这里的用户还没有身份，
    //   加守卫会把他弹回登录页，与「未注册 → 去注册」形成死循环。
    { path: '/register', name: 'register', component: () => import('../views/Register.vue') },
    { path: '/', name: 'home', component: () => import('../views/ProductList.vue') },
    { path: '/product/:id', name: 'product-detail', component: () => import('../views/ProductDetail.vue') },
    // FE2：交易链路（全部需要登录）
    {
      path: '/cart',
      name: 'cart',
      component: () => import('../views/Cart.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/checkout',
      name: 'checkout',
      component: () => import('../views/Checkout.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/orders',
      name: 'orders',
      component: () => import('../views/OrderList.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/orders/:id',
      name: 'order-detail',
      component: () => import('../views/OrderDetail.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/coupons',
      name: 'coupons',
      component: () => import('../views/Coupons.vue'),
      meta: { requiresAuth: true },
    },
    // ★ Day 58：个人中心。左侧导航 + 子路由；订单/售后/券【复用现有页面组件】，
    //   不复制一份 —— 同一份数据、同一套交互，改一处两边都变。
    {
      path: '/account',
      component: () => import('../views/Account.vue'),
      meta: { requiresAuth: true },
      redirect: '/account/overview',
      children: [
        { path: 'overview', component: () => import('../views/AccountHome.vue') },
        { path: 'orders', component: () => import('../views/OrderList.vue') },
        { path: 'refunds', component: () => import('../views/MyRefunds.vue') },
        { path: 'coupons', component: () => import('../views/Coupons.vue') },
        { path: 'reviews', component: () => import('../views/MyReviews.vue') },
        { path: 'addresses', component: () => import('../views/AccountAddresses.vue') },
        { path: 'profile', component: () => import('../views/AccountProfile.vue') },
      ],
    },
    {
      path: '/refunds',
      name: 'my-refunds',
      component: () => import('../views/MyRefunds.vue'),
      meta: { requiresAuth: true },
    },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.token) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  return true
})

export default router
