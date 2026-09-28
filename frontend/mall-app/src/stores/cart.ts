import { defineStore } from 'pinia'
import { ref } from 'vue'
import { cartList } from '../api'

/**
 * 购物车角标：只存「有效且已勾选」的件数（与 CartVO.selectedQuantity 同口径）。
 * ★ 不存金额/明细 —— 那是服务端权威数据，页面各自拉，避免两处真相。
 */
export const useCartStore = defineStore('cart', () => {
  const selectedCount = ref<number>(0)

  async function refresh() {
    try {
      const j = await cartList()
      selectedCount.value = j.data.selectedQuantity ?? 0
    } catch {
      // 未登录 / 拉取失败：角标归零即可，不做提示（列表页无购物车时会 401，跳登录已由 http 处理）
      selectedCount.value = 0
    }
  }

  function clear() {
    selectedCount.value = 0
  }

  return { selectedCount, refresh, clear }
})
