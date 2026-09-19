package com.mallx.order.vo;

import lombok.Data;

import java.math.BigDecimal;

/**
 * 订单明细行（订单详情里的 items 元素）。
 *
 * <p>★ 这里所有字段都是【快照值】，直接来自 order_items 表，
 * 不 JOIN product_skus / products —— 商品改了价、被软删，明细照原样显示。
 */
@Data
public class OrderItemVO {

    private Long id;

    private Long productId;

    private Long skuId;

    private String productName;

    private String skuName;

    private BigDecimal price;

    private Integer quantity;

    private BigDecimal totalAmount;

    private String image;
}
