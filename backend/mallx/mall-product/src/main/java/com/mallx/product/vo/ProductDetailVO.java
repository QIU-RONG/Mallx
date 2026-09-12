package com.mallx.product.vo;

import lombok.Data;
import lombok.EqualsAndHashCode;

import java.util.List;

@Data
@EqualsAndHashCode(callSuper = true)
public class ProductDetailVO extends ProductVO {
    private String description;
    private List<SkuVO> skus = List.of();
    private List<String> images = List.of();
}
