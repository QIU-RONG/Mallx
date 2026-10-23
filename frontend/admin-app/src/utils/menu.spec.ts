import { describe, expect, it } from 'vitest'
import { ADMIN_MENUS, visibleMenus } from './menu'

/**
 * ★ 菜单 × 权限码单测（Day 54）。
 *
 * <p><b>它守的故障</b>：某个入口的 `perm` 写错一个字符，或者有人给「概览」顺手加了
 * 一个不存在的码。后果不是报错，而是<b>入口静默消失</b> —— 运营会以为「系统没这个功能」，
 * 报障时说的是「后台少了东西」，排查方向会从权限表开始绕一大圈。
 *
 * <p>★ 另一条要守的是「没有码 ≠ 全看不见」：概览/商品/订单是底座，
 * 新角色只要登录就该看得到（见 `menu.ts` 的注释）。
 */
describe('admin menu · visibleMenus', () => {
  it('超级管理员（全码）→ 9 个入口全在', () => {
    const all = [
      'category:list',
      'brand:list',
      'refund:list',
      'coupon:list',
      'user:list',
      'role:list',
    ]
    expect(visibleMenus(all)).toHaveLength(ADMIN_MENUS.length)
  })

  it('★★ 没有 perms（C 端 token / 畸形 token）→ 只剩 3 个底座入口', () => {
    expect(visibleMenus([]).map((m) => m.label)).toEqual(['概览', '商品管理', '订单管理'])
  })

  it('只给 coupon:list → 券入口出现，用户/角色入口不出现', () => {
    const labels = visibleMenus(['coupon:list']).map((m) => m.label)
    expect(labels).toContain('优惠券')
    expect(labels).not.toContain('用户管理')
    expect(labels).not.toContain('角色权限')
  })

  it('每个菜单项的 path 唯一且以 / 开头（router 与菜单是同一份路径）', () => {
    const paths = ADMIN_MENUS.map((m) => m.path)
    expect(new Set(paths).size).toBe(paths.length)
    expect(paths.every((p) => p.startsWith('/'))).toBe(true)
  })

  it('★ 挂 perm 的项数固定为 6（多出来的入口必须显式登记，不能偷偷绕过权限）', () => {
    expect(ADMIN_MENUS.filter((m) => m.perm).length).toBe(6)
  })
})
