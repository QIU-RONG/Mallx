package com.mallx.order.vo;

import lombok.Data;

import java.math.BigDecimal;

/**
 * 下单时的购物车现场（{@code OrderMapper.selectSelectedCartItems} 的结果集）。
 *
 * <p>前 8 个字段是「下单要用的数据」（要写进 order_items 的快照来源）；
 * 后 4 个是「失效判定的原料」，从 SQL 里带出来给 Java 判断用。
 *
 * <p>判定顺序复刻 Day 10（先判最根本的原因）：
 * <pre>
 *   1. sku_deleted = 1        → 「规格已删除」
 *   2. product_deleted = 1    → 「商品已删除」
 *   3. product_status ≠ 1     → 「商品已下架」
 *   4. quantity &gt; available_stock → 「库存不足（仅剩 N 件）」
 * </pre>
 * ⚠️ 第 4 条只是「说人话」的提前提示，真正的防线是 inventories 的条件 UPDATE。
 */
@Data
public class OrderItemSourceVO {

    // ---------------- 下单要用的数据 ----------------

    private Long cartItemId;

    private Long skuId;

    private Long productId;

    /** products.name（快照来源） */
    private String productName;

    /** product_skus.name（快照来源，可空） */
    private String skuName;

    /** ★ 下单时的单价（快照来源） */
    private BigDecimal price;

    /** COALESCE(sku.image, product.main_image)（快照来源） */
    private String image;

    private Integer quantity;

    // ---------------- 失效判定原料 ----------------

    /** product_skus.is_deleted（软删） */
    private Integer skuDeleted;

    /** products.is_deleted（软删） */
    private Integer productDeleted;

    /** products.status（1=上架，0=下架） */
    private Integer productStatus;

    /** inventories.available_stock（实时可售） */
    private Integer availableStock;
}
