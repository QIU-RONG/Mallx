/**
 * 管理端左侧菜单的【唯一来源】（Day 54）。
 *
 * <p>★ 为什么把菜单从 `Layout.vue` 里抽出来：
 * 菜单项与权限码的对应关系是「可以写错的业务数据」，不是排版细节 ——
 * 写错了的后果是「菜单看得见、点进去 403」，或者更糟：
 * 「有权限的人看不见入口」。抽成纯数组 + 纯函数之后，它可以被单测钉住。
 *
 * <p>★★ `perm` 省略 = 不按权限码显隐，只看登录态。
 * 这一项<b>不是遗漏</b>：概览 / 商品 / 订单三个入口在当前权限种子里是
 * 「所有管理角色都有」的底座（每个种子角色都带 product:list / order:list），
 * 给它们挂码只会让新角色配错一个码就整块消失。真正需要按岗区分的
 * （分类 / 品牌 / 售后 / 券 / 用户 / 角色）才挂 perm。
 *
 * <p>⚠️ 仍然只是体验：直接敲 URL 会被后端 `@PreAuthorize` 挡成 403，
 * 而 403 在管理端是<b>常态</b>（见 `api/http.ts` 的注释），不是故障。
 */
export interface AdminMenuItem {
  /** 与 router 的 path 逐字符一致 —— el-menu 的 default-active 靠它高亮 */
  path: string
  label: string
  /** 权限码；不填 = 不按码显隐 */
  perm?: string
}

export const ADMIN_MENUS: AdminMenuItem[] = [
  { path: '/dashboard', label: '概览' },
  { path: '/products', label: '商品管理' },
  { path: '/categories', label: '分类管理', perm: 'category:list' },
  { path: '/brands', label: '品牌管理', perm: 'brand:list' },
  { path: '/shops', label: '店铺管理', perm: 'shop:list' },
  { path: '/orders', label: '订单管理' },
  { path: '/refunds', label: '售后管理', perm: 'refund:list' },
  { path: '/reviews', label: '评价管理', perm: 'review:list' },
  { path: '/coupons', label: '优惠券', perm: 'coupon:list' },
  { path: '/users', label: '用户管理', perm: 'user:list' },
  { path: '/roles', label: '角色权限', perm: 'role:list' },
  { path: '/audit-logs', label: '操作日志', perm: 'admin:list' },
]

/**
 * 按当前管理员的权限码筛出可见菜单。
 *
 * <p>★ 参数用 `readonly string[]` 而不是 `string[]`：调用方传的是 store 里的
 * `perms`，这个函数<b>不应该</b>有修改它的能力（顺带让「传常量数组」也通过类型检查）。
 */
export function visibleMenus(perms: readonly string[]): AdminMenuItem[] {
  // ★ Day 75：商户 token 带 SHOP_SCOPE_<id>，只能进商品页。
  //   平台角色没有这条权限，菜单照旧按 perm 过滤。
  const isMerchant = perms.some((p) => p.startsWith('SHOP_SCOPE_'))
  if (isMerchant) {
    return ADMIN_MENUS.filter((m) => m.label === '商品管理' || m.label === '订单管理')
  }
  return ADMIN_MENUS.filter((m) => !m.perm || perms.includes(m.perm))
}
