import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Result } from '../types/api'

/**
 * ★ http 拦截器的单测（Day 48 · 前端完善第二批）。
 *
 * <hr>
 *
 * <p><b>为什么先测它</b>：{@code http.ts} 是<b>全部 16 个页面共用的唯一出口</b>。
 * 它把后端「两套状态」的约定消化掉：
 * <pre>
 *   协议层失败：真 HTTP 401/403（响应体没有 Result 骨架）
 *   业务失败：  HTTP 200 + body.code != 200
 * ⇒ 判成功必须看 code；401 统一踢回登录页。
 * </pre>
 * 这里错一格的后果是「一整片页面同时坏」——改一个公共文件弄坏 5 个页面，
 * 而 {@code vue-tsc} 与 {@code vite build} 都看不出来（它们只保证类型和构建，不保证行为）。
 *
 * <p><b>怎么测</b>：不真发请求。mock 掉 axios 的 {@code create}，
 * 从 mock 实例上把「注册进去的两个拦截器」取出来<b>直接调用</b> ——
 * 这是测拦截器最省事也最确定的姿势：不碰网络、不碰 jsdom 的 fetch，
 * 每个用例就是一个纯粹的「给定输入 → 断言输出」。
 *
 * <p>★ 三个协作者全部 mock（router / auth store / ElMessage）：
 * 断言落在「它们有没有被以对的参数调用」上 —— 那正是 401 处理的三件事
 * （清登录态、弹提示、跳登录页）。
 */

const responseHandler = { current: null as unknown }
const errorHandler = { current: null as unknown }
const httpGet = vi.fn()
const httpPost = vi.fn()

vi.mock('axios', () => ({
  default: {
    create: () => ({
      interceptors: {
        request: { use: vi.fn() },
        response: {
          use: (onOk: unknown, onErr: unknown) => {
            responseHandler.current = onOk
            errorHandler.current = onErr
          },
        },
      },
      get: httpGet,
      post: httpPost,
    }),
  },
}))

const logout = vi.fn()
const push = vi.fn()

vi.mock('../router', () => ({
  default: {
    currentRoute: { value: { path: '/orders' } },
    push,
  },
}))

vi.mock('../stores/auth', () => ({
  useAuthStore: () => ({ token: 'test-token', logout }),
}))

const messageError = vi.fn()

vi.mock('element-plus', () => ({
  ElMessage: { error: messageError, success: vi.fn(), warning: vi.fn() },
}))

// 拿到被测模块（import 时机在两个 vi.mock 之后 ⇒ 拦截器已注册到我们的假实例上）
await import('./http')

const onOk = responseHandler.current as (r: unknown) => unknown
const onErr = errorHandler.current as (e: unknown) => unknown

/** 造一个「业务失败」的 axios 响应（HTTP 200 + code != 200）。 */
function bizResp(code: number, message: string) {
  return { data: { code, message, data: null } as Result }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('http · 业务失败（HTTP 200 + code != 200）', () => {
  it('code=200 → 原样返回 Result 骨架，不弹任何提示', () => {
    const body: Result = { code: 200, message: 'success', data: { id: 1 } }
    const out = onOk({ data: body })
    expect(out).toBe(body)
    expect(messageError).not.toHaveBeenCalled()
    expect(logout).not.toHaveBeenCalled()
  })

  it('★ code=401 → 清登录态 + 跳登录页 + 弹提示（三件事一件都不能少）', async () => {
    await expect(onOk(bizResp(401, '未登录'))).rejects.toThrow()
    expect(logout).toHaveBeenCalledTimes(1)
    expect(push).toHaveBeenCalledWith('/login')
    expect(messageError).toHaveBeenCalledWith('登录已过期，请重新登录')
  })

  it('code=400 → 只弹提示，【不】踢回登录页（业务拒绝不是登录态问题）', async () => {
    await expect(onOk(bizResp(400, '库存不足'))).rejects.toThrow()
    expect(messageError).toHaveBeenCalledWith('库存不足')
    expect(logout).not.toHaveBeenCalled()
    expect(push).not.toHaveBeenCalled()
  })
})

describe('http · 协议层失败（真 HTTP 401/403）', () => {
  it('★ HTTP 401 → 同样三件事（与业务 401 走同一条 gotoLogin，口径必须一致）', async () => {
    await expect(onErr({ response: { status: 401 } })).rejects.toThrow()
    expect(logout).toHaveBeenCalledTimes(1)
    expect(push).toHaveBeenCalledWith('/login')
    expect(messageError).toHaveBeenCalledWith('请先登录')
  })

  it('HTTP 403 → 只提示「没有权限」，不跳登录（已登录但权限不够 ≠ 未登录）', async () => {
    await expect(onErr({ response: { status: 403 } })).rejects.toThrow()
    expect(messageError).toHaveBeenCalledWith('没有权限执行此操作')
    expect(logout).not.toHaveBeenCalled()
    expect(push).not.toHaveBeenCalled()
  })

  it('HTTP 500 → 提示带状态码，方便区分「后端炸了」和「网络不通」', async () => {
    await expect(onErr({ response: { status: 500 } })).rejects.toThrow()
    expect(messageError).toHaveBeenCalledWith('请求失败：HTTP 500')
  })

  it('★ 无 response（后端没起/断网）→ 提示「请检查后端是否启动」而不是干巴巴的 network error', async () => {
    await expect(onErr(new Error('Network Error'))).rejects.toThrow()
    expect(messageError).toHaveBeenCalledWith('网络错误，请检查后端是否启动')
  })
})

describe('http · 跳转去重', () => {
  it('★ 已经在登录页时不再 push（否则 401 会反复跳转、把 redirect 冲掉）', async () => {
    const routerMod = await import('../router')
    ;(routerMod.default.currentRoute.value as { path: string }).path = '/login'
    await expect(onErr({ response: { status: 401 } })).rejects.toThrow()
    expect(push).not.toHaveBeenCalled()
    expect(logout).toHaveBeenCalledTimes(1)
    ;(routerMod.default.currentRoute.value as { path: string }).path = '/orders'
  })
})
