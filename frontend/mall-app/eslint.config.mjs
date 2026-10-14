// @ts-check
import { defineConfigWithVueTs, vueTsConfigs } from '@vue/eslint-config-typescript'

/**
 * ESLint flat config（Day 48 · 前端完善第一批）。
 *
 * <p><b>为什么现在才加</b>：此前前端只有 `vue-tsc`（类型）+ `vite build`（构建）两道关，
 * 代码确实干净（`src` 下 0 个 console.log / 0 个 any / 0 个 @ts-ignore）——
 * 但那是「靠自觉」的干净，没有任何东西在 CI 里守着它。
 * 本项目后端已经用实践证明了这条判据：**能自动发现问题的装置，比当时的干净更有价值**
 * （否则第 17 个页面、第 5 个协作者进来时，前 16 个页面立的规矩就开始漂）。
 *
 * <p><b>规则只加四条，刻意不加满</b>：
 * <ol>
 *   <li>{@code no-console} —— 放行 warn/error（生产环境需要它们），只拦 log/debug</li>
 *   <li>{@code no-explicit-any} —— error 级：本项目 VO 全是强类型，any 一出现就说明
 *       「有人绕过了 types/api.d.ts」，而那正是 Day 47 e2e 守的那条契约</li>
 *   <li>{@code no-debugger} —— 同上，遗留 debugger 是最难自查的一类</li>
 *   <li>{@code vue/no-v-html} —— error 级：XSS 的唯一入口。Vue 默认转义，
 *       只有 v-html 能关掉它，而 C 端会渲染商品名/评价内容等用户输入</li>
 * </ol>
 *
 * ⚠️ 不配 @stylistic / prettier 类规则：格式化交给各自的编辑器，
 *    在 CI 里争「换行有没有对齐」只会制造无意义的红。
 */
/**
 * ⚠️ 结构说明（第一版踩过）：`defineConfigWithVueTs` 只是「给传入的 config 加上 Vue 支持」的
 * 包装器，它自己【不提供 files 匹配】。所以必须把 `vueTsConfigs.recommended` 作为第一项传进去
 * —— files 匹配来自它；只传 `{ rules }` 会让 ESLint 报「所有文件都被忽略」。
 */
export default defineConfigWithVueTs(
  vueTsConfigs.recommended,
  {
    // ★ 显式列出要检的扩展名（recommended 已带 files，这里再收紧一次，意图更清楚）
    files: ['**/*.vue', '**/*.ts', '**/*.mts', '**/*.js'],
    rules: {
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      'no-debugger': 'error',
      '@typescript-eslint/no-explicit-any': 'error',
      'vue/no-v-html': 'error',
    },
  },
)
