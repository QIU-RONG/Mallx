import { beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * ★ 管理端路由守卫单测（Day 53）。
 *
 * <p><b>与 C 端守卫的差别</b>：C 端是「部分页面要登录」，管理端是「**全部**页面都要登录」
 * —— `/api/admin/**` 根本不在白名单里，匿名必 401。所以这里的判据只有三条：
 * <pre>
 *   非 /login 且未登录  → 去 /login
 *   /login 且已登录     → 回 /
 *   其余                → 放行
 * </pre>
 *
 * <p>★ 外加一条<b>不是转跳、却最容易漏</b>的：每次导航都要调 `auth.restore()`。
 * `perms` 不落 localStorage，只从 token 解；漏了它，**刷新后所有按钮都消失**
 * —— 页面不报错、接口也还能用（后端认 token 不认前端显隐），
 * 用户只会觉得「后台坏了」。
 *
 * <p><b>怎么测</b>：mock `vue-router` 的 `createRouter`，把注册进去的 `beforeEach`
 * 回调**抓出来直接调用** —— 不启动真路由（真路由会去碰 history 与懒加载组件）。
 */

const guardCapture = { fn: null as unknown }

vi.mock('vue-router', () => ({
  createRouter: () => ({
    beforeEach: (fn: unknown) => {
      guardCapture.fn = fn
    },
  }),
  createWebHistory: () => ({}),
}))

/** 与 router/index.ts 里读的是同一个对象 */
const state = { isLogin: false, restore: vi.fn() }

vi.mock('../stores/auth', () => ({
  useAuthStore: () => state,
}))

await import('./index')

const guard = guardCapture.fn as (to: { path: string }) => unknown

beforeEach(() => {
  vi.clearAllMocks()
  state.isLogin = false
})

describe('admin router · 登录守卫', () => {
  it('未登录访问受保护页 → 跳 /login', () => {
    expect(guard({ path: '/dashboard' })).toBe('/login')
  })

  it('未登录访问 /login → 放行', () => {
    expect(guard({ path: '/login' })).toBe(true)
  })

  it('★ 已登录访问 /login → 回 /（否则登录后按后退又停在登录页）', () => {
    state.isLogin = true
    expect(guard({ path: '/login' })).toBe('/')
  })

  it('已登录访问受保护页 → 放行', () => {
    state.isLogin = true
    expect(guard({ path: '/orders' })).toBe(true)
  })

  it('★★ 每次导航都调 restore()（漏了它 = 刷新后所有按钮消失，且不报错）', () => {
    guard({ path: '/dashboard' })
    guard({ path: '/products' })
    guard({ path: '/login' })
    expect(state.restore).toHaveBeenCalledTimes(3)
  })
})
