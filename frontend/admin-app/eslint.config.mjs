// @ts-check
import { defineConfigWithVueTs, vueTsConfigs } from '@vue/eslint-config-typescript'

/**
 * ESLint flat config —— 管理端（Day 53）。
 *
 * <p><b>为什么单独一份而不是复用 C 端的</b>：规则相同，但**风险点不同**，
 * 所以注释要写这边的理由，否则下一个人会以为「两边一样，改一处就行」。
 * 管理端多出来的两类风险：
 * <ol>
 *   <li>它会**渲染别人提交的文本**——售后拒绝原因（`remark`）、商品名、昵称。
 *       `v-html` 在本应用里的后果比 C 端更重：看到这些话的是**运营**，不是本人。</li>
 *   <li>它的 `console.log` 更容易泄露敏感上下文：管理端手里有
 *       `perms`（权限码全集）与其它用户的订单/手机号。</li>
 * </ol>
 *
 * <p><b>规则只加四条，刻意不加满</b>（与 C 端同一套判据）：
 * <ul>
 *   <li>{@code no-console} —— 放行 warn/error，只拦 log/debug</li>
 *   <li>{@code @typescript-eslint/no-explicit-any} —— error 级：VO 全是强类型，
 *       `any` 一出现就说明有人绕过了 `types/api.d.ts` 那份契约</li>
 *   <li>{@code no-debugger} —— 遗留 debugger 最难自查</li>
 *   <li>{@code vue/no-v-html} —— XSS 的唯一入口</li>
 * </ul>
 *
 * ⚠️ 不配 @stylistic / prettier 类规则：在 CI 里争「换行有没有对齐」只会制造无意义的红。
 *
 * ⚠️ 结构坑（C 端首版踩过，别重犯）：`defineConfigWithVueTs` 只是「给传入的 config 加上
 *    Vue 支持」的包装器，**它自己不提供 files 匹配**。必须把 `vueTsConfigs.recommended`
 *    作为第一项传进去 —— files 匹配来自它；只传 `{ rules }` 会让 ESLint 报
 *    「所有文件都被忽略」。
 */
export default defineConfigWithVueTs(
  vueTsConfigs.recommended,
  {
    files: ['**/*.vue', '**/*.ts', '**/*.mts', '**/*.js'],
    rules: {
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      'no-debugger': 'error',
      '@typescript-eslint/no-explicit-any': 'error',
      'vue/no-v-html': 'error',
    },
  },
)
