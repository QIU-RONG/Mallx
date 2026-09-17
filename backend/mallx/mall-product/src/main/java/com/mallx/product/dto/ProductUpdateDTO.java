package com.mallx.product.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
public class ProductUpdateDTO {

    @NotBlank(message = "商品名称不能为空")
    @Size(max = 100, message = "商品名称不能超过 100 字")
    private String name;

    private String subtitle;

    private String description;

    private String mainImage;

    /** 1=上架 0=下架 */
    private Integer status;
}