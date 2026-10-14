// 管理端类型：统一返回骨架 + 各管理端 VO / DTO
// ★ 与后端 VO 逐字段对照手写 —— 这层就是「接口契约」在前端的载体

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

// ---------- 登录 ----------
export interface LoginData {
  token: string
  tokenType: string
  expiresIn: number
  /** 管理端这里实际是 adminId（LoginVO 复用同一格） */
  userId: number
  username: string
  nickname: string
}

// ---------- 商品 ----------
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
   * ★ 在售 SKU 的价格区间 + 默认 SKU（Day 48 后端新增，与 C 端 ProductVO 同源）。
   * ⚠️ 三个都可空：商品没有在售 SKU 时全为 null ⇒ 表格要显示「无在售规格」而不是 ¥0。
   */
  minPrice?: number | null
  maxPrice?: number | null
  defaultSkuId?: number | null
}

export interface SkuVO {
  id: number
  skuCode: string
  name?: string
  price: number
  originalPrice?: number
  attributes?: Record<string, unknown>
  image?: string
  status?: number
}

export interface ProductDetailVO extends ProductVO {
  description?: string
  images: string[]
  skus: SkuVO[]
}

/** 新增商品入参（ProductCreateDTO） */
export interface ProductCreateDTO {
  categoryId: number
  brandId?: number | null
  name: string
  subtitle?: string
  description?: string
  mainImage?: string
  status?: number
  images?: string[]
  skus?: SkuCreateDTO[]
}

export interface SkuCreateDTO {
  skuCode: string
  name?: string
  price: number
  originalPrice?: number
  attributes?: Record<string, unknown>
  image?: string
  status?: number
}

/**
 * 修改商品入参（ProductUpdateDTO）—— ★ 局部更新语义：
 *   null / 不传 = 不动；[] = 清空；非空数组 = 按本次对齐。
 * 前端利用这一点：只改上下架时只发 { status }，绝不会顺手清空 SKU。
 */
export interface ProductUpdateDTO {
  name?: string
  subtitle?: string
  description?: string
  mainImage?: string
  status?: number
  images?: string[] | null
  skus?: SkuCreateDTO[] | null
}

// ---------- 订单 ----------
/** 管理端订单列表行（AdminOrderVO：★ 带 userId/userNickname，C 端 VO 没有） */
export interface AdminOrderVO {
  id: number
  orderNo: string
  userId: number
  userNickname?: string
  totalAmount: number
  payAmount: number
  status: string
  receiverName?: string
  receiverPhone?: string
  createdAt: string
}

export interface OrderItemVO {
  id: number
  skuId: number
  skuName?: string
  productName?: string
  price: number
  quantity: number
  totalAmount?: number
}

export interface OrderDetailVO {
  id: number
  orderNo: string
  userId?: number
  status: string
  totalAmount: number
  discountAmount?: number
  payAmount: number
  receiverName?: string
  receiverPhone?: string
  receiverAddress?: string
  createdAt?: string
  paidAt?: string
  shippedAt?: string
  completedAt?: string
  items: OrderItemVO[]
}

// ---------- 仪表盘 ----------
export interface DashboardOverviewVO {
  userCount: number
  productCount: number
  orderCount: number
  /** ★ 口径：payments 表 status='SUCCESS' 的 sum，不是 orders.pay_amount */
  salesAmount: number
}

export interface TrendPointVO {
  date: string
  orderCount: number
  salesAmount: number
}

// ---------- 字典 ----------
export interface CategoryVO {
  id: number
  name: string
  parentId?: number
  children?: CategoryVO[]
}

export interface BrandVO {
  id: number
  name: string
  logo?: string
}

// ===================== 售后 / 退款（Day 46） =====================
/**
 * 管理端售后单行（AdminRefundVO = RefundVO + orderNo + userNickname）。
 *
 * ★ status 与 type 用联合类型而不是 string：写错一个字符在模板里不会报错，
 *   只会静默显示空白（前端最典型的「看起来没坏」）。
 * ⚠️ 五个业务时间戳全部可空 —— 售后进度条就是靠它们画的，
 *   没走到那一步就是 null，前端必须判空而不是假定有序。
 */
export interface AdminRefundVO {
  id: number
  refundNo: string
  orderId: number
  /** 运营拿它去查订单详情 —— AdminRefundVO 比 C 端 VO 多的一列 */
  orderNo: string
  userNickname?: string
  type: 'REFUND_ONLY' | 'RETURN_REFUND'
  status: 'APPLIED' | 'APPROVED' | 'REJECTED' | 'RETURNING' | 'REFUNDING' | 'SUCCESS' | 'CANCELLED'
  /** ★ 退款额是【服务端快照】，前端传什么都不算数 */
  amount: number
  reason: string
  /** 审核备注（拒绝原因）—— 会展示给买家 */
  remark?: string
  trackingNo?: string
  appliedAt?: string
  auditedAt?: string
  shippedAt?: string
  receivedAt?: string
  refundedAt?: string
  createdAt?: string
}
