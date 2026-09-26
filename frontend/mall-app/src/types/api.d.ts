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
