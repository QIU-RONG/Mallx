import http from './http'
import type {
  AdminOrderVO,
  AdminRefundVO,
  AdminReviewVO,
  BrandCreateDTO,
  BrandUpdateDTO,
  BrandVO,
  CategoryCreateDTO,
  CategoryUpdateDTO,
  CategoryVO,
  CouponCreateDTO,
  CouponVO,
  DashboardOverviewVO,
  LoginData,
  OrderDetailVO,
  PageResult,
  PermissionVO,
  ProductCreateDTO,
  ProductDetailVO,
  ProductUpdateDTO,
  ProductVO,
  Result,
  RoleCreateDTO,
  RoleDetailVO,
  RoleUpdateDTO,
  RoleVO,
  ShopCreateDTO,
  ShopUpdateDTO,
  ShopVO,
  TrendPointVO,
  UserVO,
} from '../types/api'

// ---------- 管理端认证（★ 与 C 端是两个独立入口） ----------
export function adminLogin(username: string, password: string) {
  return http.post<never, Result<LoginData>>('/auth/admin/login', { username, password })
}

/** 商户登录（Day 75）：token 同样 type=ADMIN，perms 里多一条 SHOP_SCOPE_<id> */
export function merchantLogin(username: string, password: string) {
  return http.post<never, Result<LoginData>>('/auth/merchant/login', { username, password })
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
export function adminProductBatchStatus(ids: number[], status: 0 | 1) {
  return http.put<never, Result<number>>('/admin/products/batch-status', { ids, status })
}

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
  keyword?: string
  from?: string
  to?: string
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

// ===================== 评价审核（Day 55） =====================
/**
 * 评价分页（管理端，含已隐藏）。
 * ★ 与 C 端 `/api/products/{id}/reviews` 的口径差异：这里 status 不传 = 两者都要；
 *   C 端恒为 status=1。管理端看不见已隐藏的评价 = 「隐藏」变成单向失明。
 */
export function adminReviewPage(params: {
  current: number
  size: number
  productId?: number | null
  rating?: number | null
  status?: number | null
}) {
  return http.get<never, Result<PageResult<AdminReviewVO>>>('/admin/reviews', { params })
}

/**
 * 显示 / 隐藏一条评价。
 * ★ 只改 reviews.status，不删数据、不改内容 —— 隐藏可逆。
 * ★ 权限码 review:status 只发给超管（review:list 才给商品管理员）。
 */
export function adminReviewUpdateStatus(id: number | string, status: number) {
  return http.put<never, Result<void>>(`/admin/reviews/${id}/status`, { status })
}

// ===================== 店铺（Day 64） =====================
/** 店铺列表（含停用的；没有删除 —— 用停用代替，避免商品失去归属说明） */
export function adminShopList() {
  return http.get<never, Result<ShopVO[]>>('/admin/shops')
}

/** 新建店铺：店名 UNIQUE，重复由后端翻成 400 */
export function adminShopCreate(payload: ShopCreateDTO) {
  return http.post<never, Result<number>>('/admin/shops', payload)
}

export function adminShopUpdate(id: number | string, payload: ShopUpdateDTO) {
  return http.put<never, Result<void>>(`/admin/shops/${id}`, payload)
}

// ===================== 字典（商品表单用） =====================
export function adminCategoryTree() {
  return http.get<never, Result<CategoryVO[]>>('/admin/categories/tree')
}

export function adminBrandList() {
  return http.get<never, Result<BrandVO[]>>('/admin/brands')
}

// ===================== 分类管理（Day 54） =====================
/**
 * ★ 分类与品牌的服务端返回形状不一致，别「统一」：
 *   分类列表是【树】（children 嵌套），品牌是【平铺数组】。
 *   把树拍平是在前端做的（utils/tree.ts），因为表格/下拉需要的是扁平行。
 */
export function adminCategoryCreate(payload: CategoryCreateDTO) {
  return http.post<never, Result<number>>('/admin/categories', payload)
}

/** ★ 局部更新：parentId 传 null = 不动（后端 DTO 的既定语义），所以这里不强制带全字段 */
export function adminCategoryUpdate(id: number | string, payload: CategoryUpdateDTO) {
  return http.put<never, Result<void>>(`/admin/categories/${id}`, payload)
}

/** 删除是物理删 + 三重校验：有子分类 / 有商品引用（含软删）都会被后端 400 拒 */
export function adminCategoryDelete(id: number | string) {
  return http.delete<never, Result<void>>(`/admin/categories/${id}`)
}

// ===================== 品牌管理（Day 54） =====================
export function adminBrandCreate(payload: BrandCreateDTO) {
  return http.post<never, Result<number>>('/admin/brands', payload)
}

export function adminBrandUpdate(id: number | string, payload: BrandUpdateDTO) {
  return http.put<never, Result<void>>(`/admin/brands/${id}`, payload)
}

/** 删除是物理删：该品牌下仍有商品（含软删商品）时后端 400 */
export function adminBrandDelete(id: number | string) {
  return http.delete<never, Result<void>>(`/admin/brands/${id}`)
}

// ===================== 优惠券管理（Day 54） =====================
/**
 * ⚠️ 分页参数是 `page` 而不是 `current` —— 券的 Controller 与商品/订单/用户
 * 用的是两套参数名，照着真实签名写，别按习惯统一。
 */
export function adminCouponList(params: { page: number; size: number; status?: number | null }) {
  return http.get<never, Result<PageResult<CouponVO>>>('/admin/coupons', { params })
}

/** 建券：面额字段互斥，请求体必须先过 utils/coupon.ts#buildCouponPayload */
export function adminCouponCreate(payload: CouponCreateDTO) {
  return http.post<never, Result<number>>('/admin/coupons', payload)
}

/** ★ 已被 user_coupons 引用过的券删不掉（后端 400，不是 500） */
export function adminCouponRecords(id: number | string, page = 1, size = 10) {
  return http.get<never, Result<{
    records: Array<{
      id: number
      userId: number
      userName?: string
      status: string
      receivedAt?: string
      usedAt?: string
      orderId?: number
    }>
    total: number
  }>>(`/admin/coupons/${id}/records`, { params: { page, size } })
}

export function adminCouponUpdate(id: number | string, payload: {
  name: string
  type: string
  discountAmount?: number | null
  discountRate?: number | null
  minAmount?: number | null
  totalCount: number
  startTime: string
  endTime: string
}) {
  return http.put<never, Result<void>>(`/admin/coupons/${id}`, payload)
}

export function adminCouponEnd(id: number | string) {
  return http.put<never, Result<void>>(`/admin/coupons/${id}/end`)
}

export function adminCouponDelete(id: number | string) {
  return http.delete<never, Result<void>>(`/admin/coupons/${id}`)
}

// ===================== 用户管理（Day 54） =====================
export function adminUserPage(params: {
  current: number
  size: number
  keyword?: string
  status?: number | null
}) {
  return http.get<never, Result<PageResult<UserVO>>>('/admin/users', { params })
}

/** 管理端详情：已禁用的用户也能看 */
export function adminUserDetail(id: number | string) {
  return http.get<never, Result<UserVO>>(`/admin/users/${id}`)
}

/** ★ 定点端点（PUT /{id}/status），不是「编辑用户」：只改状态，不会覆盖昵称 */
export function adminUserUpdateStatus(id: number | string, status: number) {
  return http.put<never, Result<void>>(`/admin/users/${id}/status`, { status })
}

// ===================== 角色 / 权限（Day 54） =====================
export function adminRolePage(params: { current: number; size: number; keyword?: string }) {
  return http.get<never, Result<PageResult<RoleVO>>>('/admin/roles', { params })
}

/** 详情多带 permissionIds / permissionCodes —— 分配权限时的回显来源 */
export function adminRoleDetail(id: number | string) {
  return http.get<never, Result<RoleDetailVO>>(`/admin/roles/${id}`)
}

export function adminRoleCreate(payload: RoleCreateDTO) {
  return http.post<never, Result<number>>('/admin/roles', payload)
}

/** 编辑：name / description / status；★ code 不可改（DTO 里就没有它） */
export function adminRoleUpdate(id: number | string, payload: RoleUpdateDTO) {
  return http.put<never, Result<void>>(`/admin/roles/${id}`, payload)
}

export function adminRoleDelete(id: number | string) {
  return http.delete<never, Result<void>>(`/admin/roles/${id}`)
}

/**
 * 给角色【全量替换】权限：传的是「改完之后要有的全集」，不是增量。
 * ★ 对 SUPER_ADMIN：目标集合必须是现有集合的超集，否则后端 400（护栏②）。
 */
export function adminRoleAssignPermissions(id: number | string, permissionIds: number[]) {
  return http.put<never, Result<void>>(`/admin/roles/${id}/permissions`, { permissionIds })
}

/** 权限字典（不分页）—— 给分配权限对话框渲染勾选框 */
export function adminPermissionList() {
  return http.get<never, Result<PermissionVO[]>>('/admin/permissions')
}
