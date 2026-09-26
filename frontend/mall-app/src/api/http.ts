import axios, { type AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'
import router from '../router'
import { useAuthStore } from '../stores/auth'
import type { Result } from '../types/api'

/**
 * axios 封装 —— 后端「两套状态」约定在前端的第一道落地：
 *   · 协议层失败：真 HTTP 401/403（响应体没有 Result 骨架）
 *   · 业务失败：HTTP 200 + body.code != 200
 * ⇒ 判成功必须看 code；401 统一踢回登录页。
 *
 * 两个拦截器把以上全部消化掉，调用方只写「成功路径」：
 *   const j = await http.get('/products/1')   // j 已是 Result<T>
 */
const http = axios.create({
  baseURL: '/api',
  timeout: 15000,
})

// 请求拦截：带上 JWT（token 由 Pinia auth store 持有，localStorage 持久化）
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
      // 业务失败（HTTP 200 + code != 200）：提示 + 拒绝
      if (body.code === 401) {
        gotoLogin('登录已过期，请重新登录')
      } else {
        ElMessage.error(body.message || `操作失败（code=${body.code}）`)
      }
      return Promise.reject(new Error(body.message || `code=${body.code}`))
    }
    // ★ 直接返回 Result 骨架：调用方拿 j.data
    //（axios 拦截器签名要求 AxiosResponse —— 这里刻意换成 Result 骨架，类型断言收敛）
    return body as unknown as AxiosResponse
  },
  (err) => {
    const st = err.response?.status
    if (st === 401) {
      gotoLogin('请先登录')
    } else if (st === 403) {
      ElMessage.error('没有权限执行此操作')
    } else {
      ElMessage.error(st ? `请求失败：HTTP ${st}` : '网络错误，请检查后端是否启动')
    }
    return Promise.reject(err)
  },
)

export default http
