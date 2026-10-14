import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from './auth'

/**
 * ★ 登录态 store 的单测（Day 48 · 前端完善第二批）。
 *
 * <p><b>为什么值得单测</b>：这个 store 的状态有<b>两份</b>——
 * Pinia 的 ref（内存）和 localStorage（持久化）。它们必须同步：
 * <ul>
 *   <li>{@code setAuth} 只写内存不写 storage ⇒ 刷新页面后「明明登录过却要我重新登录」</li>
 *   <li>{@code logout} 只清内存不清 storage ⇒ <b>刷新后又变成登录态</b>（假登录），
 *       而且下一次请求会带着一个已失效的 token 打过去，换来一连串 401</li>
 * </ul>
 * 第二种是真正危险的那种：用户在 UI 上看到已退出，刷新后却登进去了 ——
 * 而 {@code vue-tsc} 对「该调 removeItem 却没调」一无所知。
 *
 * <p>★ 本文件用<b>真实的</b> Pinia + jsdom 的 localStorage，不 mock：
 * 这份同步逻辑正是要验的东西，mock 掉等于把被测对象换掉。
 */
describe('auth store · 内存与 localStorage 的同步', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('★ setAuth 后：ref 有值，localStorage 三项也都落盘', () => {
    const auth = useAuthStore()
    auth.setAuth('tok-1', 'alice', '爱丽丝')

    expect(auth.token).toBe('tok-1')
    expect(auth.username).toBe('alice')
    expect(auth.nickname).toBe('爱丽丝')
    expect(localStorage.getItem('mall_token')).toBe('tok-1')
    expect(localStorage.getItem('mall_username')).toBe('alice')
    expect(localStorage.getItem('mall_nickname')).toBe('爱丽丝')
  })

  it('nickname 省略时回落 username（不传第三个参数也要有个能显示的名字）', () => {
    const auth = useAuthStore()
    auth.setAuth('tok-2', 'bob')
    expect(auth.nickname).toBe('bob')
    expect(localStorage.getItem('mall_nickname')).toBe('bob')
  })

  it('★★ logout 后：ref 清空，localStorage 三项【全部移除】（漏一个 = 刷新后假登录）', () => {
    const auth = useAuthStore()
    auth.setAuth('tok-3', 'carol', '卡罗尔')

    auth.logout()

    expect(auth.token).toBe('')
    expect(auth.username).toBe('')
    expect(auth.nickname).toBe('')
    // ★ 三个键逐一断言，不能只断 token —— 另两个漏了不会立刻现形，
    //   但会在用户信息组件里显示上一个用户的名字
    expect(localStorage.getItem('mall_token')).toBeNull()
    expect(localStorage.getItem('mall_username')).toBeNull()
    expect(localStorage.getItem('mall_nickname')).toBeNull()
  })

  it('★ 新建 store 时从 localStorage 恢复（刷新不丢登录态）', () => {
    localStorage.setItem('mall_token', 'tok-old')
    localStorage.setItem('mall_username', 'dave')
    localStorage.setItem('mall_nickname', '戴夫')

    const auth = useAuthStore()   // 新 pinia ⇒ store 重新初始化

    expect(auth.token).toBe('tok-old')
    expect(auth.username).toBe('dave')
    expect(auth.nickname).toBe('戴夫')
  })
})
