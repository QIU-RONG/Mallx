package com.mallx.cart.vo;

import lombok.Data;
import java.math.BigDecimal;

/** 加购校验用（cross-module SQL 的返回载体，字段名对应 XML 里的 AS 别名） */
@Data
public class SkuForCartVO {
    private Long skuId;
    private String skuName;
    private BigDecimal price;
    private Integer skuDeleted;      // product_skus.is_deleted
    private Integer productStatus;   // products.status
    private Integer productDeleted;  // products.is_deleted
    private Integer availableStock;  // inventories.available_stock
}
