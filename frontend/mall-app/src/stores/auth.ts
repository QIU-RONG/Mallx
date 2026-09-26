import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * 登录态 store：token 持久化到 localStorage（刷新不丢）。
 * ★ 现阶段 C 端「必须登录」才算登录态；退出即清。
 */
export const useAuthStore = defineStore('auth', () => {
  const token = ref<string>(localStorage.getItem('mall_token') || '')
  const username = ref<string>(localStorage.getItem('mall_username') || '')
  const nickname = ref<string>(localStorage.getItem('mall_nickname') || '')

  function setAuth(t: string, u: string, n?: string) {
    token.value = t
    username.value = u
    nickname.value = n || u
    localStorage.setItem('mall_token', t)
    localStorage.setItem('mall_username', u)
    localStorage.setItem('mall_nickname', nickname.value)
  }

  function logout() {
    token.value = ''
    username.value = ''
    nickname.value = ''
    localStorage.removeItem('mall_token')
    localStorage.removeItem('mall_username')
    localStorage.removeItem('mall_nickname')
  }

  return { token, username, nickname, setAuth, logout }
})
