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
  /** 越小越靠前；0 = 默认（Day 54 管理页要显示与编辑它） */
  sortOrder?: number
  children?: CategoryVO[]
}

/** 新增分类（CategoryCreateDTO）：parentId 不传 = 顶级；只允许两级 */
export interface CategoryCreateDTO {
  parentId?: number | null
  name: string
  sortOrder?: number
}

/** 修改分类（CategoryUpdateDTO）：★ parentId 传 null 一律按「不动」处理，改不了层级 */
export interface CategoryUpdateDTO {
  parentId?: number | null
  name?: string
  sortOrder?: number
}

export interface BrandVO {
  id: number
  name: string
  logo?: string
  description?: string
  /** 1 = 启用，0 = 停用；管理端两个都返回（要能重新启用） */
  status: number
}

/** 新增品牌（BrandCreateDTO）：name 有 UNIQUE，重名由后端翻成 400 */
export interface BrandCreateDTO {
  name: string
  logo?: string
  description?: string
  status?: number
}

/** 修改品牌（BrandUpdateDTO）：status 不传 = 不动（★ 不是「停用」） */
export interface BrandUpdateDTO {
  name?: string
  logo?: string
  description?: string
  status?: number
}

// ---------- 店铺（Day 64） ----------
export interface ShopVO {
  id: number
  name: string
  logo?: string
  description?: string
  /** 1 = 启用 0 = 停用（停用只影响 C 端展示） */
  status: number
}

export interface ShopCreateDTO {
  name: string
  logo?: string
  description?: string
  status?: number
}

export interface ShopUpdateDTO {
  name?: string
  logo?: string
  description?: string
  status?: number
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

// ===================== 优惠券（Day 54 管理页） =====================
export type CouponType = 'FIXED' | 'DISCOUNT'

/**
 * 券（CouponVO，管理端列表与 C 端可领列表共用同一份字段）。
 *
 * ★ 管理端与 C 端的差别只在 WHERE（管理端含下架券），不在 VO ——
 *   所以 `status` 在 C 端恒为 1、在管理端才有 0。
 */
export interface CouponVO {
  id: number
  name: string
  type: CouponType
  discountAmount?: number | null
  /** 应付比例系数：0.8 = 打 8 折（不是 80） */
  discountRate?: number | null
  minAmount?: number | null
  totalCount: number
  receivedCount: number
  startTime: string
  endTime: string
  status: number
}

/**
 * 新建券（CouponCreateDTO）。
 * ★ 两个面额字段【互斥】：FIXED 只准带 discountAmount、DISCOUNT 只准带 discountRate，
 *   同时出现会被后端 400。前端由 `utils/coupon.ts#buildCouponPayload` 保证。
 */
export interface CouponCreateDTO {
  name: string
  type: CouponType
  discountAmount?: number
  discountRate?: number
  minAmount?: number
  totalCount: number
  startTime: string
  endTime: string
}

// ===================== 用户（Day 54 管理页） =====================
/** 用户可公开字段（UserVO）—— ★ 刻意不含 password，这是它存在的理由 */
export interface UserVO {
  id: number
  username: string
  nickname?: string
  phone?: string
  email?: string
  /** 1 = 正常，0 = 已禁用 */
  status: number
  createdAt?: string
}

// ===================== RBAC（Day 54 管理页） =====================
export interface RoleVO {
  id: number
  name: string
  /** UNIQUE；★ 不可改 —— 它已经以 ROLE_xxx 的形式签进了存量 token */
  code: string
  description?: string
  status: number
  createdAt?: string
}

export interface RoleDetailVO extends RoleVO {
  /** 该角色当前绑定的权限 id（分配权限对话框的回显依据） */
  permissionIds: number[]
  permissionCodes: string[]
}

export interface RoleCreateDTO {
  name: string
  code: string
  description?: string
}

/** 编辑角色（RoleUpdateDTO）：★ 不含 code */
export interface RoleUpdateDTO {
  name?: string
  description?: string
  status?: number
}

/**
 * 权限项（PermissionVO）—— 字典，只读。
 * ★ 权限码是代码资产：每一行 code 都必须有一个 @PreAuthorize 引用它，界面不许造码。
 */
export interface PermissionVO {
  id: number
  name: string
  code: string
  type: string
  path?: string
  method?: string
  status: number
}

// ===================== 评价审核（Day 55） =====================
/**
 * 管理端评价行（AdminReviewVO）。
 * ★ 与 C 端 ReviewVO 的唯一差别是多了 `status`：C 端恒为 1（公开列表已过滤），
 *   管理端才需要区分「正常 / 已隐藏」。
 * ⚠️ 与 C 端一样【没有 userId】：展示只用 userNickname，不暴露内部归属 id。
 */
export interface AdminReviewVO {
  id: number
  orderItemId: number
  productId: number
  productName?: string
  skuName?: string
  image?: string
  rating: number
  content?: string
  userNickname?: string
  /** 1 = 显示，0 = 已隐藏 */
  status: number
  createdAt?: string
}
