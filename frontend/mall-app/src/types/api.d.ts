// 后端统一返回骨架与核心出参类型（对照 docs/api/* 与各 VO 手写）
// ★ 字段以 Service 出参为准 —— 手写一层类型就是「接口契约」在 FE 侧的载体

export interface Result<T = unknown> {
  code: number
  message: string
  data: T
}

export interface PageResult<T> {
  records: T[]
  total: number
  current: number
  size: number
}

/** C 端商品列表项（ProductVO —— 不含价格，价格在 SKU 上） */
export interface ProductVO {
  id: number
  categoryId: number
  categoryName?: string
  brandId?: number
  brandName?: string
  name: string
  subtitle?: string
  mainImage?: string
  status: number
  /**
   * ★ 在售 SKU 的价格区间（Day 48 后端新增）。
   * ⚠️ 可空：商品所有 SKU 都停售/软删时，两个字段都是 null ——
   * 前端要按「暂无价格」渲染，【不能】当 0（那会显示成「¥0」）。
   */
  minPrice?: number | null
  maxPrice?: number | null
}

export interface SkuVO {
  id: number
  skuCode: string
  name?: string
  price: number
  originalPrice?: number
  attributes?: Record<string, unknown>
  image?: string
}

export interface ProductDetailVO extends ProductVO {
  description?: string
  skus: SkuVO[]
  images: string[]
}

export interface CategoryVO {
  id: number
  parentId?: number
  name: string
  status?: number
  children: CategoryVO[]
}

export interface BrandVO {
  id: number
  name: string
  status?: number
}

export interface LoginData {
  token: string
  userId: number
  username?: string
  nickname?: string
}

// ===================== FE2：交易链路 =====================

/** 购物车行（★ invalid 的行服务端仍返回，前端置灰且不计入结算） */
export interface CartItemVO {
  id: number
  skuId: number
  productId: number
  productName: string
  skuName?: string
  image?: string
  price: number
  quantity: number
  selected: boolean
  availableStock: number
  subtotal: number
  invalid: boolean
  invalidReason?: string
}

export interface CartVO {
  items: CartItemVO[]
  /** 所有行（含失效）数量之和 */
  totalQuantity: number
  /** ★ 有效且已勾选 的数量之和 */
  selectedQuantity: number
  /** ★ 有效且已勾选 的金额小计 */
  selectedAmount: number
}

export interface AddressVO {
  id: number
  receiverName: string
  receiverPhone: string
  province: string
  city: string
  district: string
  detailAddress: string
  isDefault?: boolean
}

export interface OrderItemVO {
  id: number
  orderId: number
  productId: number
  skuId: number
  productName: string
  skuName?: string
  price: number
  image?: string
  quantity: number
  totalAmount: number
}

/** 订单列表行 */
export interface OrderVO {
  id: number
  orderNo: string
  totalAmount: number
  payAmount: number
  /** ★ 优惠额快照：不用券是 0.00（不是 null）；pay = total - discount */
  discountAmount: number
  status: OrderStatus
  receiverName: string
  receiverPhone: string
  receiverAddress: string
  createdAt: string
}

export interface OrderDetailVO extends OrderVO {
  paidAt?: string
  shippedAt?: string
  completedAt?: string
  cancelledAt?: string
  items: OrderItemVO[]
}

export type OrderStatus =
  | 'PENDING_PAYMENT'
  | 'PAID'
  | 'SHIPPED'
  | 'COMPLETED'
  | 'CANCELLED'

/** 券面（可领列表） */
export interface CouponVO {
  id: number
  name: string
  type: string
  discountAmount?: number
  discountRate?: number
  minAmount?: number
  totalCount?: number
  receivedCount?: number
  startTime?: string
  endTime?: string
  status?: number
}

/** 我的券（领取记录 + 券面快照；id 就是下单要用的 userCouponId） */
export interface UserCouponVO {
  id: number
  couponId: number
  couponName: string
  type: string
  discountAmount?: number
  discountRate?: number
  minAmount?: number
  status: 'UNUSED' | 'USED' | 'EXPIRED'
  receivedAt?: string
  usedAt?: string
  orderId?: number
  endTime?: string
  expired?: boolean
}

export interface PaymentVO {
  id: number
  orderId: number
  payNo?: string
  amount: number
  method: string
  status?: string
  paidAt?: string
  createdAt?: string
}

// ===================== 售后 / 退款（Day 46） =====================
/**
 * 买家视角的售后单（RefundVO）。
 *
 * ★ 与 AdminRefundVO 的差别：管理端多 orderNo / userNickname，
 *   这两个是【别人的信息】，C 端 VO 一律不带（与 OrderVO / AdminOrderVO 同构）。
 *
 * ⚠️ 五个时间戳都可空 —— 进度条靠它们画，没走到那一步就是 null。
 */
export interface RefundVO {
  id: number
  refundNo: string
  orderId: number
  type: 'REFUND_ONLY' | 'RETURN_REFUND'
  status: 'APPLIED' | 'APPROVED' | 'REJECTED' | 'RETURNING' | 'REFUNDING' | 'SUCCESS' | 'CANCELLED'
  /** ★ 服务端按 orders.pay_amount 算的快照 —— 前端传什么都不算数 */
  amount: number
  reason: string
  /** 审核备注（拒绝原因） */
  remark?: string
  trackingNo?: string
  appliedAt?: string
  auditedAt?: string
  shippedAt?: string
  receivedAt?: string
  refundedAt?: string
  createdAt?: string
}
