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

    /**
     * ★ 默认 SKU id（= 最便宜的那个在售 SKU），供列表「快捷加购」用（Day 48）。
     *
     * <p>★ 它与 {@link #minPrice} <b>同源</b>：前端显示「¥9999 起」时，
     * 一键加购进车里的就是 9999 那个规格 —— 取「第一个 SKU」会造成
     * 「显示 9999、加进去 12499」的对不上账。
     *
     * <p>⚠️ 可为 null（没有在售 SKU 时），前端必须与 minPrice 一起判，
     * 不能假定它一定有值。
     */
    private Long defaultSkuId;
}
