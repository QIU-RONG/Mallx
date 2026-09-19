package com.mallx.order.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.mallx.order.entity.OrderItem;

/**
 * 订单明细 Mapper
 *
 * <p>纯单表操作，全部由 {@link BaseMapper} 覆盖，【不需要 XML】。
 * 对外只暴露 {@code insert}（下单）与 {@code selectList}（详情）。
 */
public interface OrderItemMapper extends BaseMapper<OrderItem> {
}
