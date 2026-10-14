package com.mallx.product.vo;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;

/**
 * 商品的价格区间（Day 48 · 给列表补价格）。
 *
 * <p><b>为什么需要它</b>：{@code products} 表【没有价格列】—— 价格挂在 SKU 上
 * （一件商品可以有多个规格，各卖各的价）。所以商品列表要显示价格，
 * 必须对 {@code product_skus} 做一次 GROUP BY 聚合。
 *
 * <p>★ 这也是「C 端商品列表此前只有一个裸卡片、没有价格」的根因：
 * 不是前端偷懒，是 {@code ProductVO} 里根本没有这个字段。
 *
 * <p>⚠️ {@code @NoArgsConstructor} 不能省：这个类走手写 XML 的
 * {@code resultType}（不是 {@code resultMap}），MyBatis 靠<b>无参构造 + setter</b> 回填，
 * 少了它会在运行时报 "No constructor found"。
 */
@Data
@NoArgsConstructor
public class ProductPriceRangeVO {

    private Long productId;

    /** 在售 SKU 的最低价（前端显示「¥ 199 起」）。 */
    private BigDecimal minPrice;

    /** 在售 SKU 的最高价（与 minPrice 相等时前端不显示「起」）。 */
    private BigDecimal maxPrice;
}
