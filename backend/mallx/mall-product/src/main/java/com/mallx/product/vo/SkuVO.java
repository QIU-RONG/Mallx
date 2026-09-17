package com.mallx.product.vo;

import lombok.Data;

import java.math.BigDecimal;
import java.util.Map;

/**
 * SKU 出参。
 * <p>
 * ⚠️ {@code attributes} 的类型必须与实体 {@code ProductSku.attributes} <b>保持一致</b>。
 * Service 里是用 {@code BeanUtils.copyProperties(sku, sv)} 做搬运的，
 * 类型不匹配时它会<b>静默跳过</b>这个字段 —— 详情接口的 attributes 变成 null，且不报任何错。
 */
@Data
public class SkuVO {
    private Long id;
    private String skuCode;
    private String name;
    private BigDecimal price;
    private BigDecimal originalPrice;
    private Map<String, Object> attributes;
    private String image;
}
