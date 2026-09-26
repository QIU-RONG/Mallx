import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    // ★ 开发期代理：/api 全部转发到后端 8080 —— 同源策略下免 CORS 配置，
    //   与生产「nginx 反代」同一思路。C 端应用 5173，管理端应用用 5174。
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true,
      },
    },
  },
})
