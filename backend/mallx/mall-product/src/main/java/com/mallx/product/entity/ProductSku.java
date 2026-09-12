package com.mallx.product.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

@Data
@TableName("product_skus")
public class ProductSku {
    @TableId(type = IdType.AUTO)
    private Long id;

    private Long productId;

    private String skuCode;

    private String name;

    private BigDecimal price;

    private BigDecimal originalPrice;

    private String attributes;

    private String image;

    private Integer status;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;

    @TableField(fill =  FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedAt;

}
