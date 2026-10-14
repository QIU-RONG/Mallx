package com.mallx.product.vo;

import lombok.Data;

import java.math.BigDecimal;

@Data
public class ProductVO {
    private Long id;
    private Long categoryId;

    private String categoryName;

    private Long brandId;

    private String brandName;

    private String name;

    private String subtitle;

    private String mainImage;

    private Integer status;

    /**
     * ★ 在售 SKU 的最低价 / 最高价（Day 48 新增）。
     *
     * <p><b>为什么商品列表必须有它</b>：{@code products} 表<u>没有价格列</u>，
     * 价格挂在 SKU 上 ⇒ 不聚合就只能在列表上放一张没有数字的卡片。
     * 这不是前端偷懒，是 VO 里压根没这个字段。
     *
     * <p>★ 由 {@code ProductServiceImpl#fillPrices} 批量填充（一次 GROUP BY 拿整页，
     * 不做 N+1）。<b>没有任何在售 SKU 的商品这两个字段为 null</b> ——
     * 前端要按「可能为空」处理，不能当 0 显示（0 元会让人以为白送）。
     *
     * <p>★ 两者相等时前端不显示「起」字：只有一个规格的商品说「¥199 起」很怪。
     */
    private BigDecimal minPrice;

    private BigDecimal maxPrice;
}
