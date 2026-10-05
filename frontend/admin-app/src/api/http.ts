import axios, { type AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'
import router from '../router'
import { useAuthStore } from '../stores/auth'
import type { Result } from '../types/api'

/**
 * 管理端 axios 封装 —— 与 C 端同骨架，但多一层「权限码」语义：
 *
 *   匿名 / token 过期      → 真 HTTP 401（过滤器层）→ 踢回管理端登录
 *   登录但无该权限码       → 真 HTTP 403（AccessDeniedHandler）→ 「无此权限」提示
 *   有权限但业务不成立     → HTTP 200 + body.code != 200 → 提示 body.message
 *
 * ★ 关键：管理端 403 是「常态」而非异常（超管之外的账号本来就少码），
 *   所以这里对 403 给的是明确文案，不做 logout —— 换个功能照样能用。
 */
const http = axios.create({
  baseURL: '/api',
  timeout: 15000,
})

http.interceptors.request.use((cfg) => {
  const auth = useAuthStore()
  if (auth.token) {
    cfg.headers.Authorization = `Bearer ${auth.token}`
  }
  return cfg
})

function gotoLogin(reason: string) {
  const auth = useAuthStore()
  auth.logout()
  ElMessage.error(reason)
  if (router.currentRoute.value.path !== '/login') {
    router.push('/login')
  }
}

http.interceptors.response.use(
  (resp) => {
    const body = resp.data as Result
    if (body && typeof body.code === 'number' && body.code !== 200) {
      if (body.code === 401) {
        gotoLogin('登录已过期，请重新登录')
      } else {
        ElMessage.error(body.message || `操作失败（code=${body.code}）`)
      }
      return Promise.reject(new Error(body.message || `code=${body.code}`))
    }
    // ★ 直接吐 Result 骨架：调用方拿 j.data
    return body as unknown as AxiosResponse
  },
  (err) => {
    const st = err.response?.status
    if (st === 401) {
      gotoLogin('请先以管理员身份登录')
    } else if (st === 403) {
      // ★ 管理端专属文案：403 = 当前管理员没有被授予这个权限码
      ElMessage.error('权限不足：当前账号没有该操作的权限码')
    } else {
      ElMessage.error(st ? `请求失败：HTTP ${st}` : '网络错误，请检查后端是否启动')
    }
    return Promise.reject(err)
  },
)

export default http
