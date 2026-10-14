import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

/**
 * ★ 路由守卫的单测（Day 48 · 前端完善第二批）。
 *
 * <p><b>为什么值得单测</b>：{@code beforeEach} 是全站<b>唯一</b>的「未登录不准进」防线，
 * 7 个交易链路页面（cart / checkout / orders / order-detail / coupons / refunds）都靠
 * {@code meta.requiresAuth} 这一个标记。守卫错一格的后果：
 * <ul>
 *   <li>该拦的没拦 ⇒ 未登录用户能进结算页，然后在提交时才拿到一个 401</li>
 *   <li>redirect 丢了 ⇒ 用户登录后落在首页而不是他本来要去的页面（体验断层）</li>
 * </ul>
 * 这两类都不会让类型检查或构建失败 —— 只有真的点一遍才能发现。
 *
 * <p>★ 视图组件 mock 成空壳：只关心守卫的判定，不想把 9 个页面的依赖树都拉起来。
 * 懒加载路由只有被导航到才会 import，所以这里只需 mock 用到的两个。
 */
vi.mock('../views/Login.vue', () => ({ default: { name: 'LoginStub' } }))
vi.mock('../views/OrderList.vue', () => ({ default: { name: 'OrderListStub' } }))
vi.mock('../views/ProductList.vue', () => ({ default: { name: 'ProductListStub' } }))

const router = (await import('./index')).default
const { useAuthStore } = await import('../stores/auth')

beforeEach(async () => {
  localStorage.clear()
  setActivePinia(createPinia())
  await router.push('/')            // 回到一个干净页面，避免上一个用例的导航状态残留
  await router.isReady()
})

describe('router 守卫 · requiresAuth', () => {
  it('★ 未登录访问 /orders → 被拦截到 /login，且 redirect 带回原路径', async () => {
    await router.push('/orders')

    expect(router.currentRoute.value.path).toBe('/login')
    // ★ redirect 是体验的关键：少了它，用户登录后会落在首页，
    //   而不是他刚才想去的订单页 —— 而没有任何类型错误会提示这件事
    expect(router.currentRoute.value.query.redirect).toBe('/orders')
  })

  it('★★ 已登录访问 /orders → 放行，不出现 redirect', async () => {
    const auth = useAuthStore()
    auth.setAuth('tok-1', 'alice')

    await router.push('/orders')

    expect(router.currentRoute.value.path).toBe('/orders')
    expect(router.currentRoute.value.query.redirect).toBeUndefined()
  })

  it('公开页（/ 与 /login）未登录也能进（守卫只拦带标记的路由）', async () => {
    await router.push('/login')
    expect(router.currentRoute.value.path).toBe('/login')
    await router.push('/')
    expect(router.currentRoute.value.path).toBe('/')
  })
})
