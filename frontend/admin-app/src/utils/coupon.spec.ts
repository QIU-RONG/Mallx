import { describe, expect, it } from 'vitest'
import { buildCouponPayload, couponFaceText, type CouponForm } from './coupon'

/**
 * ★ 优惠券表单转换单测（Day 54）。
 *
 * <p><b>最有价值的两条</b>是「按类型丢弃另一个字段」：
 * 后端对「FIXED 同时带 discountRate」和「DISCOUNT 同时带 discountAmount」
 * 都直接 400。而界面上切换类型<b>不清空</b>上一个输入 —— 没有这层过滤，
 * 用户会看到一个自相矛盾的报错（「我明明没填折扣率」）。
 */
const base: CouponForm = {
  name: '满 100 减 20',
  type: 'FIXED',
  discountAmount: 20,
  discountRate: null,
  minAmount: 100,
  totalCount: 100,
  timeRange: ['2026-10-01T00:00:00', '2026-10-31T23:59:59'],
}

describe('coupon · buildCouponPayload', () => {
  it('FIXED → 带 discountAmount，且【绝不】带 discountRate', () => {
    const r = buildCouponPayload(base)
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.payload).toMatchObject({ type: 'FIXED', discountAmount: 20, minAmount: 100 })
    expect(r.payload).not.toHaveProperty('discountRate')
  })

  it('★★ FIXED 表单里残留的 discountRate 不会下发（切换类型的经典事故）', () => {
    const r = buildCouponPayload({ ...base, discountRate: 0.8 })
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.payload).not.toHaveProperty('discountRate')
  })

  it('DISCOUNT → 带 discountRate，且【绝不】带 discountAmount（同样有残留值）', () => {
    const r = buildCouponPayload({
      ...base,
      type: 'DISCOUNT',
      discountAmount: 20,
      discountRate: 0.8,
      name: '全场 8 折',
    })
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.payload).toMatchObject({ type: 'DISCOUNT', discountRate: 0.8 })
    expect(r.payload).not.toHaveProperty('discountAmount')
  })

  it('折扣率边界：1.00 合法（不打折）；1.01 / 0 非法', () => {
    const mk = (rate: number) =>
      buildCouponPayload({ ...base, type: 'DISCOUNT', discountRate: rate })
    expect(mk(1).ok).toBe(true)
    expect(mk(1.01).ok).toBe(false)
    expect(mk(0).ok).toBe(false)
  })

  it('结束时间 <= 开始时间 → 拒绝（不能靠后端兜底，否则表单已经关了一半）', () => {
    const r = buildCouponPayload({
      ...base,
      timeRange: ['2026-10-31T23:59:59', '2026-10-01T00:00:00'],
    })
    expect(r).toEqual({ ok: false, error: '结束时间必须晚于开始时间' })
  })

  it('券名只有空格 → 拒绝（后端 @NotBlank 也拦，但前端要先说人话）', () => {
    const r = buildCouponPayload({ ...base, name: '   ' })
    expect(r.ok).toBe(false)
  })

  it('发行总量 0 合法（占位券），负数 / 小数非法', () => {
    expect(buildCouponPayload({ ...base, totalCount: 0 }).ok).toBe(true)
    expect(buildCouponPayload({ ...base, totalCount: -1 }).ok).toBe(false)
    expect(buildCouponPayload({ ...base, totalCount: 1.5 }).ok).toBe(false)
  })

  it('门槛为 null 时不下发该字段（后端按「不限」处理）', () => {
    const r = buildCouponPayload({ ...base, minAmount: null })
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.payload).not.toHaveProperty('minAmount')
  })
})

describe('coupon · couponFaceText', () => {
  it('满减券显示金额，去掉无意义的 .00', () => {
    expect(couponFaceText({ type: 'FIXED', discountAmount: 20, discountRate: null })).toBe('¥20')
  })

  it('折扣券把 0.8 显示成 8 折（不是 80% —— 券面惯例是「几折」）', () => {
    expect(couponFaceText({ type: 'DISCOUNT', discountAmount: null, discountRate: 0.8 })).toBe('8 折')
    expect(couponFaceText({ type: 'DISCOUNT', discountAmount: null, discountRate: 0.75 })).toBe(
      '7.5 折',
    )
  })

  it('折扣率为 1 → 不打折（而不是 10 折）', () => {
    expect(couponFaceText({ type: 'DISCOUNT', discountAmount: null, discountRate: 1 })).toBe(
      '不打折',
    )
  })

  it('字段缺失时给「缺失」而不是 ¥0 / NaN（宁可难看，不可误导）', () => {
    expect(couponFaceText({ type: 'FIXED', discountAmount: null, discountRate: null })).toBe(
      '面额缺失',
    )
    expect(couponFaceText({ type: 'DISCOUNT', discountAmount: null, discountRate: null })).toBe(
      '折扣缺失',
    )
  })
})
