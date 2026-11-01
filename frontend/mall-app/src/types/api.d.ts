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
  /**
   * ★ 默认 SKU id（= 最便宜的在售 SKU），供列表「快捷加购」用（Day 48 后端新增）。
   * ⚠️ 与 minPrice 【同源】：显示「¥9999 起」时加进车里的就是 9999 那个规格。
   * 同样可空 —— 与 minPrice 一起判。
   */
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
}

export interface ProductDetailVO extends ProductVO {
  description?: string
  skus: SkuVO[]
  images: string[]
  /** 所属店铺（Day 64）；没有店铺的商品两个字段都可能为空 */
  shopId?: number | null
  shopName?: string | null
}

/** 店铺（Day 81，C 端展示用） */
/** 收藏列表行（Day 82） */
export interface FavoriteVO {
  productId: number
  name?: string
  mainImage?: string | null
  status?: number
  minPrice?: number | null
  maxPrice?: number | null
  defaultSkuId?: number | null
  createdAt?: string
}

export interface ShopVO {
  id: number
  name: string
  logo?: string | null
  description?: string | null
  status?: number
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

// ===================== Day 52：手机号验证码 =====================

/**
 * 发码结果。
 *
 * ★★ `devCode` **只在非 prod 有值**（后端用 `acceptsProfiles("prod")` 卡住）——
 *   本机 / CI 没有短信服务商，总得有办法拿到码，所以开发期把它放进响应。
 *   前端据此自动填入并提示；生产环境拿到的是 `null`，界面自然不显示任何提示。
 *   ⚠️ 一个会在响应里返回验证码的登录接口等于没有验证码 —— 接真实短信后此字段应整体删除。
 */
export interface SmsSendData {
  devCode?: string | null
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

/** 「我的资料」（`GET /api/users/me`）—— ★ 不含密码哈希，出参白名单由后端 UserVO 保证 */
export interface UserVO {
  id: number
  username: string
  nickname?: string
  phone?: string
  email?: string
  status: number
  createdAt?: string
}

/** AI 客服回答（POST /api/ai/chat） */
export interface AiChatReply {
  reply: string
  /** mock = 未接大模型（规则回复）；llm = 真实模型 */
  mode: 'mock' | 'llm' | string
  /** 本轮执行过的工具名 */
  tools: string[]
  /** Day 110：知识库引用来源与耗时 */
  sources?: Array<{ source: string; heading?: string }>
  elapsedMs?: number
}

export interface AiChatTurn {
  role: 'user' | 'assistant'
  content: string
}

/** 商品评价（ReviewVO）—— 公开列表与「我的评价」共用同一份字段 */
export interface ReviewVO {
  id: number
  orderItemId: number
  productId: number
  productName?: string
  skuName?: string
  image?: string
  rating: number
  content?: string
  userNickname?: string
  createdAt?: string
  /** Day 80：晒图 URL 列表 */
  images?: string[]
  /** Day 89：有用数 / 我是否点过 */
  likeCount?: number
  liked?: boolean
}

/** 商品评价列表（带聚合） */
export interface ReviewPageVO {
  avgRating?: number | null
  reviewCount: number
  records: ReviewVO[]
  total: number
  current: number
  size: number
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
  /** Day 65：列表首件商品摘要（后端一次 IN 查询批量补，不是前端 N+1） */
  firstItemName?: string | null
  firstItemSkuName?: string | null
  firstItemImage?: string | null
  /** 明细行数，>1 时列表显示「等 N 件」 */
  itemCount?: number | null
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
  | 'REFUNDED'

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
