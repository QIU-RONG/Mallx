import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Result } from '../types/api'

/**
 * ★ 管理端 http 拦截器单测（Day 53）。
 *
 * <hr>
 *
 * <p><b>为什么必须重写而不是抄 C 端那份</b>：骨架相同，但<b>语义相反</b>。
 * <pre>
 *   C 端：业务失败 → 弹提示；401 → 踢登录；403 → 「没权限」
 *   管理端：多一条铁律 —— ★★ 403 是【常态】，不是异常
 * </pre>
 * 超管之外的账号本来就只被授予少数权限码，点到一个没授权的功能是<b>正常工作状态</b>。
 * 如果 403 也走 {@code gotoLogin}（清登录态 + 跳登录页），运营点错一个菜单就被踢出后台
 * —— 而这<b>不会报错、不会告警</b>，只会被当成「系统老掉线」。
 *
 * <p>⇒ 本文件最值钱的一条就是「协议 403：只提示，不 logout、不跳转」。
 *
 * <p><b>怎么测</b>：不真发请求。mock 掉 axios 的 {@code create}，把注册进去的两个拦截器
 * 取出来<b>直接调用</b> —— 每个用例就是一个纯粹的「给定输入 → 断言输出」。
 */

const responseHandler = { current: null as unknown }
const errorHandler = { current: null as unknown }

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
      get: vi.fn(),
      post: vi.fn(),
    }),
  },
}))

const logout = vi.fn()
const push = vi.fn()
/**
 * ★★ `push` 必须挂在【default 对象上】，不能只作为具名导出：
 *    http.ts 写的是 `import router from '../router'` → `router.push(...)`，
 *    具名导出在 default 对象上根本不存在（第一版就栽在这，
 *    报 `TypeError: default.push is not a function`，两条 401 用例一起红）。
 * ★ `currentRoute.value` 也必须是同一个对象 —— 测「跳转去重」时靠改它的 path。
 */
const routerStub = { currentRoute: { value: { path: '/dashboard' } }, push }

vi.mock('../router', () => ({ default: routerStub }))

vi.mock('../stores/auth', () => ({
  useAuthStore: () => ({ token: 'admin-token', logout }),
}))

const messageError = vi.fn()

vi.mock('element-plus', () => ({
  ElMessage: { error: messageError, success: vi.fn(), warning: vi.fn() },
}))

// 拿到被测模块（动态 import 发生在上面那些 const 初始化之后 ⇒ mock 工厂能安全引用它们）
const httpMod = await import('./http')
void httpMod

const onOk = responseHandler.current as (r: unknown) => unknown
const onErr = errorHandler.current as (e: unknown) => unknown

/** 造一个「业务失败」的 axios 响应（HTTP 200 + code != 200）。 */
function bizResp(code: number, message: string) {
  return { data: { code, message, data: null } as Result }
}

beforeEach(() => {
  vi.clearAllMocks()
  // 每个用例都从「不在登录页」开始，避免用例互相污染（跳转去重那条会改它）
  routerStub.currentRoute.value.path = '/dashboard'
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

  it('code=400 → 只弹提示，不踢回登录页（业务拒绝不是登录态问题）', async () => {
    await expect(onOk(bizResp(400, '该订单状态不允许发货'))).rejects.toThrow()
    expect(messageError).toHaveBeenCalledWith('该订单状态不允许发货')
    expect(logout).not.toHaveBeenCalled()
    expect(push).not.toHaveBeenCalled()
  })
})

describe('http · 协议层失败（真 HTTP 401/403）', () => {
  it('HTTP 401 → 三件事（与业务 401 走同一条 gotoLogin，口径必须一致）', async () => {
    await expect(onErr({ response: { status: 401 } })).rejects.toThrow()
    expect(logout).toHaveBeenCalledTimes(1)
    expect(push).toHaveBeenCalledWith('/login')
    expect(messageError).toHaveBeenCalledWith('请先以管理员身份登录')
  })

  it('★★ HTTP 403 → 只提示「权限不足」，【不】logout、【不】跳登录（管理端 403 是常态）', async () => {
    await expect(onErr({ response: { status: 403 } })).rejects.toThrow()
    expect(messageError).toHaveBeenCalledWith('权限不足：当前账号没有该操作的权限码')
    // 这两条是本文件存在的全部理由：403 被误当成 401 处理，运营点错一个菜单就被踢出后台
    expect(logout).not.toHaveBeenCalled()
    expect(push).not.toHaveBeenCalled()
  })

  it('HTTP 500 → 提示带状态码（区分「后端炸了」与「网络不通」）', async () => {
    await expect(onErr({ response: { status: 500 } })).rejects.toThrow()
    expect(messageError).toHaveBeenCalledWith('请求失败：HTTP 500')
  })

  it('★ 无 response（后端没起/断网）→ 提示「请检查后端是否启动」', async () => {
    await expect(onErr(new Error('Network Error'))).rejects.toThrow()
    expect(messageError).toHaveBeenCalledWith('网络错误，请检查后端是否启动')
  })
})

describe('http · 跳转去重', () => {
  it('★ 已经在登录页时不再 push（否则 401 会反复跳转、把 redirect 冲掉）', async () => {
    routerStub.currentRoute.value.path = '/login'
    await expect(onErr({ response: { status: 401 } })).rejects.toThrow()
    expect(push).not.toHaveBeenCalled()
    expect(logout).toHaveBeenCalledTimes(1)
  })
})
