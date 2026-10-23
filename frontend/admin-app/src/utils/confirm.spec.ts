import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ElMessageBox } from 'element-plus'
import { confirmAction } from './confirm'

/**
 * ★ 二次确认单测（Day 54）—— 守的是「取消 = 执行」这个已经发生过的事故。
 *
 * <p>现状（改造前）的写法是：
 * <pre>
 *   await ElMessageBox.confirm(...).catch(() => null)
 *   await api.execute()      // 取消也执行
 * </pre>
 * 它<b>不报错、不告警</b>，只会在某天对账时发现「怎么多退了一笔」。
 * 所以这里断言的不是「弹窗长什么样」，而是<b>返回值与后续动作之间的因果关系</b>：
 * 取消必须得到 `false`，且<b>不抛异常</b>（抛了调用方就得多写一层 try）。
 */
vi.mock('element-plus', () => ({
  ElMessageBox: { confirm: vi.fn() },
}))

const confirmMock = vi.mocked(ElMessageBox.confirm)

beforeEach(() => {
  confirmMock.mockReset()
})

describe('confirmAction', () => {
  it('用户点「确定」→ true', async () => {
    confirmMock.mockResolvedValueOnce({} as never)
    await expect(confirmAction('要删吗？')).resolves.toBe(true)
  })

  it('★★ 用户点「取消」→ false，且【不抛异常】（旧写法在这里会继续执行删除/退款）', async () => {
    confirmMock.mockRejectedValueOnce('cancel')
    // ★★ 不要写成 `expect(async () => ...).not.toThrow()`：
    //    toThrow 不 await 返回的 Promise ⇒ 无论里面发生什么都会 PASS（假绿）。
    //    本日控制组第 ④ 组正是靠这条抓到了它自己的第一版（见 Day-54 文档 §5）。
    //    `.resolves` 同时覆盖两件事：不抛异常（否则 resolves 失败）+ 返回值是 false。
    await expect(confirmAction('要删吗？')).resolves.toBe(false)
  })

  it('点 X / ESC（同样走 reject）→ 也必须是 false', async () => {
    confirmMock.mockRejectedValueOnce('close')
    await expect(confirmAction('要删吗？')).resolves.toBe(false)
  })

  it('把文案、标题与按钮文字原样交给弹窗（危险动作要能自定义「确认退款」）', async () => {
    confirmMock.mockResolvedValueOnce({} as never)
    await confirmAction('将退款 ¥20，不可撤销', {
      title: '执行退款',
      type: 'error',
      confirmButtonText: '确认退款',
      cancelButtonText: '再想想',
    })
    expect(confirmMock).toHaveBeenCalledWith('将退款 ¥20，不可撤销', '执行退款', {
      type: 'error',
      confirmButtonText: '确认退款',
      cancelButtonText: '再想想',
    })
  })

  it('默认值：标题「提示」、warning、确定 / 取消', async () => {
    confirmMock.mockResolvedValueOnce({} as never)
    await confirmAction('继续？')
    expect(confirmMock).toHaveBeenCalledWith('继续？', '提示', {
      type: 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
  })
})
