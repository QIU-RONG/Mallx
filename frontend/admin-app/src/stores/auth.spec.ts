import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from './auth'

/**
 * ★ 管理端 auth store 单测（Day 53）。
 *
 * <p><b>它为什么值得测</b>：`perms`（权限码数组）是**全部按钮显隐的唯一依据**，
 * 而它<b>不落 localStorage</b> —— 只从 token 里解。于是有两个高发故障：
 * <ol>
 *   <li>**刷新后所有按钮消失**：token 还在、但内存里的 perms 是空的，
 *       没人调 `restore()` 就永远不恢复（这是本文件最后两条守的东西）；</li>
 *   <li>★★ **拿 C 端 token 混进后台**：`decodePerms` 里的 `type !== 'ADMIN'` 判断
 *       就是为了拦它。漏了它，一个普通买家的 token 会被当管理端身份用
 *       —— 后端当然还会 403，但前端会把「无权限」显示成一堆空白按钮，
 *       让人以为是前端 bug 而不是越权尝试。</li>
 * </ol>
 *
 * <p>★ `atob` 不用 mock：jsdom 自带（Node 的 WHATWG 实现），
 * 我们顺带验证了「去掉 `=` padding 的 base64url 能解」这条真实性质。
 */

const TOKEN_KEY = 'mallx_admin_token'
const USER_KEY = 'mallx_admin_user'

/** 造一个形如真 JWT 的串：`h.<base64url(payload)>.s`（不带 padding，与真 token 一致） */
function jwt(payload: unknown): string {
  const b64 = btoa(JSON.stringify(payload))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
  return `h.${b64}.s`
}

const ADMIN_TOKEN = jwt({ type: 'ADMIN', perms: ['product:list', 'order:list'] })
const USER_TOKEN = jwt({ type: 'USER', perms: ['product:list'] })

beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
})

describe('adminAuth · decodePerms（经 login 入口）', () => {
  it('type=ADMIN 的 token → perms 被解出来', () => {
    const s = useAuthStore()
    s.login({ token: ADMIN_TOKEN, username: 'admin' } as never)
    expect(s.perms).toEqual(['product:list', 'order:list'])
    expect(s.token).toBe(ADMIN_TOKEN)
    expect(s.username).toBe('admin')
  })

  it('★★ type=USER（C 端 token）→ perms 必须为空（防混进后台）', () => {
    const s = useAuthStore()
    s.login({ token: USER_TOKEN, username: 'buyer' } as never)
    expect(s.perms).toEqual([])
    expect(s.hasPerm('product:list')).toBe(false)
  })

  it('★ 畸形 token（不是三段）→ 返回空数组且【不抛异常】', () => {
    const s = useAuthStore()
    expect(() => s.login({ token: 'not-a-jwt', username: 'x' } as never)).not.toThrow()
    expect(s.perms).toEqual([])
  })

  it('★ payload 不是合法 JSON → 同样空数组且不抛（防止一个坏 token 让整个后台白屏）', () => {
    const s = useAuthStore()
    expect(() => s.login({ token: 'h.%%%.s', username: 'x' } as never)).not.toThrow()
    expect(s.perms).toEqual([])
  })
})

describe('adminAuth · hasPerm', () => {
  it('有该码 → true；没有 → false', () => {
    const s = useAuthStore()
    s.login({ token: ADMIN_TOKEN, username: 'admin' } as never)
    expect(s.hasPerm('product:list')).toBe(true)
    expect(s.hasPerm('refund:approve')).toBe(false)
  })
})

describe('adminAuth · logout', () => {
  it('清内存 + 清 localStorage（漏清 storage = 刷新后又登进去了）', () => {
    const s = useAuthStore()
    s.login({ token: ADMIN_TOKEN, username: 'admin' } as never)
    s.logout()
    expect(s.token).toBe('')
    expect(s.username).toBe('')
    expect(s.perms).toEqual([])
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull()
    expect(localStorage.getItem(USER_KEY)).toBeNull()
  })
})

describe('adminAuth · restore（刷新恢复）', () => {
  it('★★ 只有 token 在 localStorage 时，restore() 必须把 perms 解回来', () => {
    // 模拟「F5 刷新」：storage 里还留着 token，但内存 store 刚创建、perms 是空的
    localStorage.setItem(TOKEN_KEY, ADMIN_TOKEN)
    localStorage.setItem(USER_KEY, 'admin')
    setActivePinia(createPinia())
    const s = useAuthStore()
    expect(s.token).toBe(ADMIN_TOKEN)
    expect(s.perms).toEqual([]) // ← 刷新后的真实状态：还没人调 restore
    s.restore()
    expect(s.perms).toEqual(['product:list', 'order:list'])
    expect(s.hasPerm('order:list')).toBe(true)
  })

  it('没有 token 时 restore() 不炸，perms 保持空', () => {
    const s = useAuthStore()
    expect(() => s.restore()).not.toThrow()
    expect(s.perms).toEqual([])
  })
})
