import http from './http'
import type {
  AdminOrderVO,
  BrandVO,
  CategoryVO,
  DashboardOverviewVO,
  LoginData,
  OrderDetailVO,
  PageResult,
  ProductCreateDTO,
  ProductDetailVO,
  ProductUpdateDTO,
  ProductVO,
  Result,
  TrendPointVO,
} from '../types/api'

// ---------- 管理端认证（★ 与 C 端是两个独立入口） ----------
export function adminLogin(username: string, password: string) {
  return http.post<never, Result<LoginData>>('/auth/admin/login', { username, password })
}

// ===================== 商品管理 =====================
/** status 不传 = 全部（含下架）—— 与 C 端「写死 status=1」正好相反 */
export function adminPageProducts(params: {
  current: number
  size: number
  categoryId?: number
  keyword?: string
  status?: number | null
}) {
  return http.get<never, Result<PageResult<ProductVO>>>('/admin/products', { params })
}

/** 管理端详情：下架商品也能看（getAdminDetail 不判 status） */
export function adminProductDetail(id: number | string) {
  return http.get<never, Result<ProductDetailVO>>(`/admin/products/${id}`)
}

export function adminProductCreate(payload: ProductCreateDTO) {
  return http.post<never, Result<number>>('/admin/products', payload)
}

/** ★ 局部更新：只发要改的字段（下架 = { status: 0 }） */
export function adminProductUpdate(id: number | string, payload: ProductUpdateDTO) {
  return http.put<never, Result<void>>(`/admin/products/${id}`, payload)
}

export function adminProductDelete(id: number | string) {
  return http.delete<never, Result<void>>(`/admin/products/${id}`)
}

// ===================== 订单管理 =====================
export function adminOrderList(params: {
  page: number
  size: number
  status?: string
  userId?: number
}) {
  return http.get<never, Result<PageResult<AdminOrderVO>>>('/admin/orders', { params })
}

export function adminOrderDetail(id: number | string) {
  return http.get<never, Result<OrderDetailVO>>(`/admin/orders/${id}`)
}

/** 管理端取消：仅待支付单，已支付会被 CAS 挡成 400 */
export function adminOrderCancel(id: number | string) {
  return http.post<never, Result<void>>(`/admin/orders/${id}/cancel`)
}

/**
 * 发货 —— ★ 路径在 /api/orders 下而不是 /api/admin/orders：
 * 它是 C 端 Controller 里唯一挂 @PreAuthorize('order:ship') 的方法。
 * 前端就照后端真实路径写，别想当然加 /admin 前缀。
 */
export function adminOrderShip(id: number | string) {
  return http.post<never, Result<void>>(`/orders/${id}/ship`)
}

// ===================== 仪表盘 =====================
export function dashboardOverview() {
  return http.get<never, Result<DashboardOverviewVO>>('/admin/dashboard/overview')
}

export function dashboardTrend(days = 7) {
  return http.get<never, Result<TrendPointVO[]>>('/admin/dashboard/trend', { params: { days } })
}

// ===================== 字典（商品表单用） =====================
export function adminCategoryTree() {
  return http.get<never, Result<CategoryVO[]>>('/admin/categories/tree')
}

export function adminBrandList() {
  return http.get<never, Result<BrandVO[]>>('/admin/brands')
}
