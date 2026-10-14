// ★ 从 vitest/config 而不是 vite 导入 defineConfig —— Vite 自己的 UserConfigExport
//   【不含 test 字段】，直接写 test 会让 vue-tsc 报 TS2769（'test' does not exist in type）。
//   vitest/config 的 defineConfig 是同一个函数的类型增强版，vite build 完全不受影响。
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

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
  test: {
    // ★ jsdom：auth store 要碰 localStorage、router 要碰 history，Node 环境没有这些
    environment: 'jsdom',
    // ★ 只扫 src 下的 *.spec.ts —— 与后端「测试不与实现混放」同一思路：
    //   实现文件里不会因为叫 *.spec.ts 被误扫进来
    include: ['src/**/*.spec.ts'],
  },
})
