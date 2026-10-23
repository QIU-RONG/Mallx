import { ElMessageBox } from 'element-plus'

/**
 * 二次确认的【唯一正确写法】（Day 54）。
 *
 * <p>★★ 这条工具函数的存在，是因为项目里已经有一个<b>真实事故</b>：
 * <pre>
 *   await ElMessageBox.confirm('确定删除？', ...).catch(() => null)
 *   await api.delete(id)          // ← 用户点了「取消」，这行照样执行
 * </pre>
 * `confirm` 在<b>取消时 reject</b>；`.catch(() => null)` 把这次 reject 吞掉之后，
 * 函数继续往下走 —— 于是「取消」等于「确认」。最危险的一处是售后的
 * 「执行退款」：点了「再想想」，钱照样退出去。
 *
 * <p>★ 所以约定：<b>凡是要根据用户选择决定「做不做」的地方，一律用本函数</b>，
 * 它把两种结果收敛成布尔值，调用方写成 `if (!ok) return`。
 * 不要再用「confirm().catch(...) 然后继续执行」的形状。
 *
 * <p>⚠️ 提示文案由调用方给（要写清后果，尤其是不可撤销的动作）；
 * 这里只管「问」和「答案」，不猜业务。
 */
export interface ConfirmOptions {
  title?: string
  type?: 'warning' | 'error' | 'info' | 'success'
  confirmButtonText?: string
  cancelButtonText?: string
}

export async function confirmAction(message: string, opts: ConfirmOptions = {}): Promise<boolean> {
  try {
    await ElMessageBox.confirm(message, opts.title ?? '提示', {
      type: opts.type ?? 'warning',
      // ★ 「危险动作」的按钮文案要能自解释：确定 / 取消 太容易点错
      confirmButtonText: opts.confirmButtonText ?? '确定',
      cancelButtonText: opts.cancelButtonText ?? '取消',
    })
    return true
  } catch {
    // 取消、点 X、按 ESC 都走这里 —— 一律视为「不做」
    return false
  }
}
