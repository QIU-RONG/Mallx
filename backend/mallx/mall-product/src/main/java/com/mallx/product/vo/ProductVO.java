package com.mallx.product.vo;

import lombok.Data;

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
}
