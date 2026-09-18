package com.mallx.cart.vo;

import lombok.Data;

import java.math.BigDecimal;

/**
 * 购物车行（对客户端展示）。
 *
 * <p>前 10 个字段由 {@code CartItemMapper.selectCartView} 的 XML 结果集直接映射
 * （列别名 → 驼峰，靠 yml 的 {@code map-underscore-to-camel-case}）；
 * {@code subtotal / invalid / invalidReason} 三个由 Service 计算后回填。
 *
 * <p>末尾三个 {@code *Deleted / productStatus} 是「失效判定的原料」，
 * 从 SQL 里带出来给 Java 判断用。它们会出现在 JSON 响应里（无害）；
 * 想藏起来给这三个字段加 {@code @JsonIgnore} 即可。
 */
@Data
public class CartItemVO {

    private Long id;                 // cart_items.id
    private Long skuId;              // cart_items.sku_id
    private Long productId;          // product_skus.product_id
    private String productName;      // products.name
    private String skuName;          // product_skus.name（如「黑色 256GB」）
    private String image;            // COALESCE(sku.image, product.main_image)
    private BigDecimal price;        // ★ 实时价
    private Integer quantity;
    private Boolean selected;
    private Integer availableStock;  // ★ 实时库存（inventories.available_stock）

    // ---------------- 以下三个由 Service 算，不来自 XML ----------------

    /** price × quantity（服务端算，禁止客户端计算金额） */
    private BigDecimal subtotal;

    /** ★ 是否失效：失效项仍要返回（前端置灰），但不计入结算金额 */
    private boolean invalid;

    /** 失效原因：「规格已删除」/「商品已删除」/「商品已下架」/「库存不足（仅剩 N 件）」 */
    private String invalidReason;

    // ---------------- 以下三个是「失效判定的原料」 ----------------

    /** product_skus.is_deleted（软删） */
    private Integer skuDeleted;

    /** products.is_deleted（软删） */
    private Integer productDeleted;

    /** products.status（1=上架，0=下架） */
    private Integer productStatus;
}
