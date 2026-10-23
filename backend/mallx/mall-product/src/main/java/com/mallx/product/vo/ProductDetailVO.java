package com.mallx.product.vo;

import lombok.Data;
import lombok.EqualsAndHashCode;

import java.util.List;

@Data
@EqualsAndHashCode(callSuper = true)
public class ProductDetailVO extends ProductVO {
    /** Day 64：商品所属店铺（可空 = 未归属）。shopName 由装配时补 */
    private Long shopId;
    private String shopName;
    private String description;
    private List<SkuVO> skus = List.of();
    private List<String> images = List.of();
}
