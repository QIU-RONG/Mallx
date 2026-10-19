// ★ 从 vitest/config 导入 defineConfig —— Vite 自己的 UserConfigExport **不含 test 字段**，
//   直接写 test 会让 vue-tsc 报 TS2769（'test' does not exist in type）。
//   C 端 Day 48 就是「只跑了 lint + test，没重跑 build」而被 CI 抓到的，
//   所以这次改完必须把 build 也跑一遍。
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

// 管理端应用：5174（C 端 mall-app 是 5173）
// ★ 与 C 端同思路：dev 用 vite proxy 把 /api 转发到后端 8080 ——
//   同源 ⇒ 免 CORS；生产换 nginx 反代即可，前端代码零改动。
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5174,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true,
      },
    },
  },
  test: {
    // ★ jsdom：auth store 要碰 localStorage 与 atob（解 JWT），router 要碰 history
    environment: 'jsdom',
    include: ['src/**/*.spec.ts'],
  },
})
