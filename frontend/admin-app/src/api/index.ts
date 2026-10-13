import http from './http'
import type {
  AdminOrderVO,
  AdminRefundVO,
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

// ===================== 售后 / 退款（Day 46） =====================
/**
 * 全部挂在 /api/admin/** 下 —— ★ 不是排版偏好，是安全要求：
 * SecurityConfig 白名单里有 GET /api/products/** 与 /api/categories/** 的 permitAll，
 * 管理端接口若挂到 C 端前缀下会【静默变成匿名可访问】。
 *
 * ⚠️ 四个写端点各一个权限码，后端不做「审核=打款」的合码
 * （不相容职务分离）：approve / reject / receive / refund。
 * 前端这里也只是【按钮显隐】，真正的边界在后端 @PreAuthorize。
 */
export function adminRefundList(params: {
  page: number
  size: number
  status?: string
  userId?: number
}) {
  return http.get<never, Result<PageResult<AdminRefundVO>>>('/admin/refunds', { params })
}

/** 审核通过：仅退款 → 可执行退款；退货退款 → 等买家寄回 */
export function adminRefundApprove(id: number, remark?: string) {
  return http.post<never, Result<void>>(`/admin/refunds/${id}/approve`, null, {
    params: { remark },
  })
}

/** 审核拒绝（终态）：★ remark 会展示给买家，所以入参必填（前端拦一次，后端不强制） */
export function adminRefundReject(id: number, remark: string) {
  return http.post<never, Result<void>>(`/admin/refunds/${id}/reject`, null, {
    params: { remark },
  })
}

/** 退货确认收货：已寄出 → 可执行退款 */
export function adminRefundReceive(id: number) {
  return http.post<never, Result<void>>(`/admin/refunds/${id}/receive`)
}

/** ★★★ 执行退款 —— 全项目唯一动钱的售后端点（订单→REFUNDED、库存回补、退券、负向流水） */
export function adminRefundExecute(id: number) {
  return http.post<never, Result<void>>(`/admin/refunds/${id}/refund`)
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
