import type { CouponCreateDTO, CouponVO } from '../types/api'

/**
 * 优惠券表单 → 请求体的【纯转换层】（Day 54）。
 *
 * <p>★ 为什么值得单独抽出来：`POST /api/admin/coupons` 有一条只有 Service 才知道的
 * 关系校验 ——
 * <pre>
 *   FIXED    → discountAmount 必须非 null，discountRate 必须为 null
 *   DISCOUNT → discountRate   必须非 null，discountAmount 必须为 null
 * </pre>
 * 只要两个都带上，后端直接 400（`CouponServiceImpl#validateTypeFields` 附近的判断）。
 * 而界面上切换券类型时，<b>上一个类型填的值还留在表单里</b> —— 这是最容易漏的一处：
 * 用户先看「满减」填了 20，再切成「折扣」，提交时 20 跟着一起发出去 ⇒ 建券失败，
 * 报错文案还叫「折扣券不能同时填写 discountAmount」，用户会说「我明明没填」。
 *
 * <p>⇒ 所以由这个函数<b>按类型只挑该有的那个字段</b>，界面上的残留值一律不下发。
 * 它是纯函数，因此可以被单测逐条钉住（见 `coupon.spec.ts`）。
 */
export type CouponType = 'FIXED' | 'DISCOUNT'

export interface CouponForm {
  name: string
  type: CouponType
  /** 满减面额；type=DISCOUNT 时即使有值也不会被下发 */
  discountAmount: number | null
  /** 折扣率，应付比例系数：0.8 = 打 8 折；type=FIXED 时即使有值也不会被下发 */
  discountRate: number | null
  /** 使用门槛，null = 不限 */
  minAmount: number | null
  totalCount: number
  /** el-date-picker(datetimerange) 的值；未选 = null */
  timeRange: [string, string] | null
}

export type CouponPayloadResult =
  | { ok: true; payload: CouponCreateDTO }
  | { ok: false; error: string }

/** 校验并把表单转换成请求体；不合法时返回可直接弹给用户的中文原因 */
export function buildCouponPayload(form: CouponForm): CouponPayloadResult {
  const name = form.name.trim()
  if (!name) return { ok: false, error: '券名不能为空' }

  if (!Number.isInteger(form.totalCount) || form.totalCount < 0) {
    return { ok: false, error: '发行总量必须是不小于 0 的整数（0 表示先占位、暂不可领）' }
  }

  if (!form.timeRange) return { ok: false, error: '请选择可领取的时间段' }
  const [startTime, endTime] = form.timeRange
  // ★ 字符串比较在这个格式（yyyy-MM-ddTHH:mm:ss）下与时间先后一致
  if (endTime <= startTime) return { ok: false, error: '结束时间必须晚于开始时间' }

  const base: CouponCreateDTO = {
    name,
    type: form.type,
    totalCount: form.totalCount,
    startTime,
    endTime,
  }
  if (form.minAmount != null) base.minAmount = form.minAmount

  if (form.type === 'FIXED') {
    if (form.discountAmount == null || form.discountAmount <= 0) {
      return { ok: false, error: '满减券请填写大于 0 的面额' }
    }
    return { ok: true, payload: { ...base, discountAmount: form.discountAmount } }
  }

  if (form.discountRate == null || form.discountRate <= 0 || form.discountRate > 1) {
    return { ok: false, error: '折扣率必须在 0 到 1 之间（0.8 表示打 8 折）' }
  }
  return { ok: true, payload: { ...base, discountRate: form.discountRate } }
}

/** 券面文案：列表里第一眼要看懂「这张券值多少」 */
export function couponFaceText(c: Pick<CouponVO, 'type' | 'discountAmount' | 'discountRate'>): string {
  if (c.type === 'FIXED') {
    if (c.discountAmount == null) return '面额缺失'
    return `¥${Number(c.discountAmount.toFixed(2))}`
  }
  if (c.discountRate == null) return '折扣缺失'
  if (c.discountRate >= 1) return '不打折'
  // ★ 0.75*10 可能是 7.500000000000001，先四舍五入到一位小数再判断是否是整数
  const zhe = Math.round(c.discountRate * 100) / 10
  return Number.isInteger(zhe) ? `${zhe} 折` : `${zhe.toFixed(1)} 折`
}
