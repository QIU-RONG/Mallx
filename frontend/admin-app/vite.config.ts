import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

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
})
