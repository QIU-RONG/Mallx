import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { LoginData } from '../types/api'

const TOKEN_KEY = 'mallx_admin_token'
const USER_KEY = 'mallx_admin_user'

/**
 * 管理端登录态。
 *
 * ★ 与 C 端最大的差别：管理端 token 里带 `perms` claim（权限码数组）
 *   —— C 端 token 的 perms 是空的，所以 C 端应用【不能】靠前端判权限。
 * 这里把 perms 解出来，用于「按钮级显隐」（如没有 product:create 就不显示新建按钮）。
 *
 * ⚠️ 必须强调：前端显隐只是体验，不是安全边界。
 *    真正的边界是后端每个端点上的 @PreAuthorize('...')；
 *    ★★ 管理端「读接口也要权限」，与 C 端「GET 公开」正好相反。
 */
export const useAuthStore = defineStore('adminAuth', () => {
  const token = ref<string>(localStorage.getItem(TOKEN_KEY) || '')
  const username = ref<string>(localStorage.getItem(USER_KEY) || '')
  const perms = ref<string[]>([])

  /** 解 JWT payload 取 perms / type（只解不断言签名 —— 签名由后端校验） */
  function decodePerms(tk: string): string[] {
    try {
      const payload = tk.split('.')[1]
      if (!payload) return []
      const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'))
      const claims = JSON.parse(json) as { perms?: string[]; type?: string }
      // ★ 只有 type=ADMIN 的 token 才算管理端身份：防止拿 C 端 token 混进后台
      if (claims.type !== 'ADMIN') return []
      return claims.perms || []
    } catch {
      return []
    }
  }

  function apply(tk: string, name: string) {
    token.value = tk
    username.value = name
    perms.value = decodePerms(tk)
    localStorage.setItem(TOKEN_KEY, tk)
    localStorage.setItem(USER_KEY, name)
  }

  function login(data: LoginData) {
    apply(data.token, data.username)
  }

  function logout() {
    token.value = ''
    username.value = ''
    perms.value = []
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  }

  /** 恢复刷新后的 perms（token 还在 localStorage，但内存 store 是空的） */
  function restore() {
    if (token.value) perms.value = decodePerms(token.value)
  }

  const isLogin = computed(() => !!token.value)
  const hasPerm = (code: string) => perms.value.includes(code)

  return { token, username, perms, isLogin, login, logout, restore, hasPerm }
})
