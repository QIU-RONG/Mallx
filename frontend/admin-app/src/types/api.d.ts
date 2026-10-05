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
