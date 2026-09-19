package com.mallx.order.service;

import com.mallx.order.dto.OrderCreateDTO;

/**
 * 订单服务
 */
public interface OrderService {

    /**
     * 从购物车下单：把当前用户【已勾选】的购物车项结算成一张订单。
     *
     * <p>整个方法在一个事务里完成：校验地址 → 读选中项 → 失效校验 → 算金额
     * → 按 skuId 升序锁库存 → 插 orders + order_items → 清购物车选中项。
     *
     * @return 新订单 id
     */
    Long createFromCart(Long userId, OrderCreateDTO dto);
}
