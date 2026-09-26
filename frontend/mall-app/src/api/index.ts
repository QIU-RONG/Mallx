import http from './http'
import type { BrandVO, CategoryVO, LoginData, PageResult, ProductDetailVO, ProductVO, Result } from '../types/api'

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
