package com.mallx.product.vo;

import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/** 收藏列表行（Day 82） */
@Data
public class FavoriteVO {

    private Long productId;

    private String name;

    private String mainImage;

    private Integer status;

    private BigDecimal minPrice;

    private BigDecimal maxPrice;

    private Long defaultSkuId;

    private LocalDateTime createdAt;
}
