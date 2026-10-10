package com.mallx.order.vo;

import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 售后域回补库存要用的订单明细（Day 46）—— 只有两个字段。
 *
 * <p>★ 为什么只给两列：退款回补库存需要的是「哪个 SKU、退几件」，
 * 就这两个数。商品名、成交价快照、SKU 规格串……售后域<b>一个都不需要</b>。
 * 给它一个 {@code OrderItem} 实体，等于把订单明细的内部形状暴露给外部模块 ——
 * 以后 {@code order_items} 加一列，售后域也会被牵连。
 * ★ 这就是「跨模块只开一扇<b>窄</b>门面」：宽度由<b>调用方要做什么</b>决定，
 *   不是由「我这张表有什么」决定（与 {@code OrderItemBuyContext} 同一个道理）。
 *
 * <p>⚠️ {@code @NoArgsConstructor} 必须显式写 —— 它做 {@code resultType}，
 * 靠「反射无参构造 + setter」装填（本项目所有 VO 的同一条规矩）。
 *
 * <p>⚠️ 别名一律<b>下划线</b>（{@code sku_id} / {@code quantity}）：
 * 这是唯一在 {@code map-underscore-to-camel-case} 两种配置下都成立的写法。
 */
@Data
@NoArgsConstructor
public class OrderRefundItem {

    /** SKU 主键 */
    private Long skuId;

    /** 这一行买了几件 —— 也是要回补给 {@code available} 的数量 */
    private Integer quantity;
}
