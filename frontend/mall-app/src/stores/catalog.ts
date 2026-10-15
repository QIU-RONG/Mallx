import { defineStore } from 'pinia'
import { ref } from 'vue'
import { categoryTree } from '../api'
import type { CategoryVO } from '../types/api'

/**
 * ★ 分类树缓存（Day 50）。
 *
 * <p><b>为什么要有这个 store</b>：改造后顶栏多了一条**品类导航**，它和商品列表页的
 * 「分类下拉」需要同一份分类树。各请求一次的话，进首页会打两次同一个接口
 * （而且两次返回还不一定同时到，理论上会出现顶栏与下拉不一致的一瞬）。
 *
 * <p>★ 用「已加载就不再请求」而不是「设 TTL」：分类是**低频变更**数据，
 * 一次会话内不会变；真要变，刷新页面即可。
 * （对比：商品详情走 Redis 代次键，正因为商品会被运营频繁改 —— 两种数据的
 * 「保鲜要求」不同，解法当然也不同。）
 */
export const useCatalogStore = defineStore('catalog', () => {
  const tree = ref<CategoryVO[]>([])
  /** ★ 普通变量而非 ref：它只用于"要不要发请求"的判断，不参与渲染 */
  let loaded = false

  async function ensure(): Promise<CategoryVO[]> {
    if (loaded) return tree.value
    try {
      const r = await categoryTree()
      tree.value = r.data
      loaded = true
    } catch {
      // ★ 失败不抛：顶栏没有品类也不该让整页崩 —— 商品列表是它自己的请求
      tree.value = []
    }
    return tree.value
  }

  return { tree, ensure }
})
