import type { CategoryVO } from '../types/api'

/**
 * 分类树拍平（Day 54 从 `ProductList.vue` 的内联实现提出来）。
 *
 * <p>★ 为什么提出来：商品表单（选择分类）与分类管理页（选择父分类）
 * 需要的是<b>同一个</b>结果。两处各写一遍的后果不是「多几行」，
 * 而是某天一处改了缩进/排序、另一处没有 —— 同一棵树上两个下拉的选项顺序不一致，
 * 这类「看起来都正常」的漂移最难被报障。
 *
 * <p>★ 缩进用全角空格（U+3000）：`el-select` 的 label 不走 HTML，
 * 普通空格会被连续折叠，层级就看不出来了。
 */
export function flattenCategories(list: readonly CategoryVO[]): CategoryVO[] {
  const out: CategoryVO[] = []
  const walk = (nodes: readonly CategoryVO[], depth: number) => {
    for (const c of nodes) {
      out.push({ ...c, name: `${'　'.repeat(depth)}${c.name}` })
      if (c.children?.length) walk(c.children, depth + 1)
    }
  }
  walk(list, 0)
  return out
}
