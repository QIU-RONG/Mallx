import http from './http'
import type {
  AddressVO,
  BrandVO,
  CartVO,
  CategoryVO,
  CouponVO,
  LoginData,
  OrderDetailVO,
  OrderVO,
  PageResult,
  PaymentVO,
  ProductDetailVO,
  ProductVO,
  RefundVO,
  Result,
  UserCouponVO,
} from '../types/api'

// ---------- 认证 ----------
export function login(username: string, password: string) {
  return http.post<never, Result<LoginData>>('/auth/login', { username, password })
}

// ---------- 商品（白名单只读，匿名可看） ----------
export function pageProducts(params: { current: number; size: number; categoryId?: number; keyword?: string }) {
  return http.get<never, Result<PageResult<ProductVO>>>('/products', { params })
}

export function productDetail(id: number | string) {
  return http.get<never, Result<ProductDetailVO>>(`/products/${id}`)
}

export function searchProducts(params: {
  current: number
  size: number
  keyword?: string
  categoryId?: number
}) {
  return http.get<never, Result<PageResult<ProductVO>>>('/products/search', { params })
}

// ---------- 分类树 / 品牌字典（白名单只读） ----------
export function categoryTree() {
  return http.get<never, Result<CategoryVO[]>>('/categories/tree')
}

export function brandList() {
  return http.get<never, Result<BrandVO[]>>('/brands')
}

// ===================== FE2：购物车 =====================
export function cartList() {
  return http.get<never, Result<CartVO>>('/cart')
}

export function cartAdd(skuId: number, quantity = 1) {
  return http.post<never, Result<number>>('/cart', { skuId, quantity })
}

export function cartUpdateQuantity(id: number, quantity: number) {
  return http.put<never, Result<void>>(`/cart/${id}`, { quantity })
}

export function cartUpdateSelected(id: number, selected: boolean) {
  return http.put<never, Result<void>>(`/cart/${id}/selected`, { selected })
}

export function cartRemove(id: number) {
  return http.delete<never, Result<void>>(`/cart/${id}`)
}

// ===================== FE2：地址 =====================
export function addressList() {
  return http.get<never, Result<AddressVO[]>>('/addresses')
}

export function addressCreate(payload: Omit<AddressVO, 'id'>) {
  return http.post<never, Result<number>>('/addresses', payload)
}

// ===================== FE2：订单 =====================
/** ★ 买什么只认购物车里 selected 的行，入参只有 addressId（+ 可选 userCouponId） */
export function orderCreate(addressId: number, userCouponId?: number | null) {
  return http.post<never, Result<number>>('/orders', {
    addressId,
    userCouponId: userCouponId ?? null,
  })
}

export function orderList(params: { current: number; size: number; status?: string }) {
  return http.get<never, Result<PageResult<OrderVO>>>('/orders', { params })
}

export function orderDetail(id: number | string) {
  return http.get<never, Result<OrderDetailVO>>(`/orders/${id}`)
}

export function orderCancel(id: number | string) {
  return http.post<never, Result<void>>(`/orders/${id}/cancel`)
}

export function orderConfirm(id: number | string) {
  return http.post<never, Result<void>>(`/orders/${id}/confirm`)
}

// ===================== FE2：支付 =====================
/** ★ 金额只由服务端取 orders.pay_amount —— 请求体里没有 amount */
export function payOrder(orderId: number, method: 'ALIPAY' | 'WECHAT' | 'BALANCE' = 'BALANCE') {
  return http.post<never, Result<PaymentVO>>('/payments', { orderId, method })
}

// ===================== FE2：优惠券 =====================
export function couponAvailable(params: { page: number; size: number }) {
  return http.get<never, Result<PageResult<CouponVO>>>('/coupons', { params })
}

export function couponReceive(couponId: number) {
  return http.post<never, Result<void>>(`/coupons/${couponId}/receive`)
}

export function couponMy(params: { page: number; size: number }) {
  return http.get<never, Result<PageResult<UserCouponVO>>>('/coupons/my', { params })
}

// ===================== FE3：售后 / 退款（Day 46） =====================
/**
 * C 端售后接口全部挂在 /api/refunds 下（不是 /api/admin/refunds —— 那是运营入口）。
 *
 * ★★ 为什么 C 端接口【一个 @PreAuthorize 都没有】：C 端 token 的 perms 是空集，
 *   挂上权限码等于把所有买家全挡在门外。C 端的边界是【数据归属】——
 *   每条 SQL 都带 `AND user_id = #{userId}`，别人的单在你这里就是「不存在」。
 *   ⇒ 前端同理：这里不需要也【不能】做权限显隐，只需要按订单状态决定能不能申请。
 */

/** 申请售后 —— ★ 只传 orderId / type / reason，没有金额字段（退款额由服务端按订单实付算） */
export function refundApply(payload: { orderId: number; type: string; reason: string }) {
  return http.post<never, Result<number>>('/refunds', payload)
}

export function myRefunds(params: { page: number; size: number }) {
  return http.get<never, Result<PageResult<RefundVO>>>('/refunds/my', { params })
}

export function refundDetail(id: number | string) {
  return http.get<never, Result<RefundVO>>(`/refunds/${id}`)
}

/** 撤销申请（只在 APPLIED/APPROVED 有效，后端 CAS 挡） */
export function refundCancel(id: number) {
  return http.post<never, Result<void>>(`/refunds/${id}/cancel`)
}

/** 退货寄出：填物流单号（仅【退货退款】在【审核通过】后可用） */
export function refundShip(id: number, trackingNo: string) {
  return http.post<never, Result<void>>(`/refunds/${id}/ship`, { trackingNo })
}
