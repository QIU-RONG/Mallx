package com.mallx.cart.service;

import com.mallx.cart.dto.CartAddDTO;
import com.mallx.cart.vo.CartVO;

public interface CartService {

    /** 加入购物车；返回购物车行 id。同 SKU 自动合并数量 */
    Long addToCart(Long userId, CartAddDTO dto);

    /** 购物车列表：实时价/库存 + 失效标记 + 服务端算小计与总计 */
    CartVO getCart(Long userId);

    /**
     * 修改某行数量。数量不可超过实时库存。
     * <p>★ 必须先验明「这行是不是你的」，不是则抛 404（不是 403）
     */
    void updateQuantity(Long userId, Long itemId, Integer quantity);

    /** 勾选 / 取消勾选某行。同样要先验 ownerId */
    void updateSelected(Long userId, Long itemId, Boolean selected);

    /** 删除某行（物理删：cart_items 没有 is_deleted）。同样要先验 ownerId */
    void removeItem(Long userId, Long itemId);
}
