package com.mallx.product.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.mallx.product.handler.JsonbMapTypeHandler;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.Map;

/**
 * 商品 SKU 实体，映射 product_skus 表。
 * <p>
 * ⚠️ {@code autoResultMap = true} 不能省：MyBatis-Plus 查询时默认用自动生成的 resultMap，
 * 它<b>不认</b>自定义 TypeHandler。只加 {@code @TableField(typeHandler = ...)} 只解决"写"，
 * 不解决"读" —— 写库一切正常，回头查详情发现 attributes 是空的，而且不报任何错。
 */
@Data
@TableName(value = "product_skus", autoResultMap = true)
public class ProductSku {
    @TableId(type = IdType.AUTO)
    private Long id;

    private Long productId;

    private String skuCode;

    private String name;

    private BigDecimal price;

    private BigDecimal originalPrice;

    /** 动态规格：DB 列是 jsonb，Java 侧是 Map，靠 JsonbMapTypeHandler 互相翻译 */
    @TableField(typeHandler = JsonbMapTypeHandler.class)
    private Map<String, Object> attributes;

    private String image;

    private Integer status;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;

    @TableField(fill =  FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedAt;


    @TableLogic
    private Integer isDeleted;

}
