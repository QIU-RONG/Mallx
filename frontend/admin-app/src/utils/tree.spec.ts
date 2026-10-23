import { describe, expect, it } from 'vitest'
import { flattenCategories } from './tree'
import type { CategoryVO } from '../types/api'

const tree: CategoryVO[] = [
  {
    id: 1,
    name: '手机',
    children: [
      { id: 11, name: '旗舰', parentId: 1, children: [] },
      { id: 12, name: '折叠屏', parentId: 1, children: [] },
    ],
  },
  { id: 2, name: '电脑', children: [] },
]

describe('flattenCategories', () => {
  it('先序遍历：父在前、子紧随其后（与表格的行顺序一致）', () => {
    expect(flattenCategories(tree).map((c) => c.id)).toEqual([1, 11, 12, 2])
  })

  it('子级按深度前缀全角空格；顶级不加', () => {
    const flat = flattenCategories(tree)
    expect(flat[0].name).toBe('手机')
    expect(flat[1].name).toBe('　旗舰')
  })

  it('不修改原对象（页面 reconcile 后仍要拿原树渲染表格）', () => {
    const before = tree[0].name
    flattenCategories(tree)
    expect(tree[0].name).toBe(before)
  })

  it('空树 → 空数组', () => {
    expect(flattenCategories([])).toEqual([])
  })
})
