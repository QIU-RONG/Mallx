package com.mallx.product.vo;

import lombok.Data;

import java.math.BigDecimal;

@Data
public class SkuVO {
    private Long id;
    private String skuCode;
    private String name;
    private BigDecimal price;
    private BigDecimal originalPrice;
    private String attributes;
    private String image;
}
