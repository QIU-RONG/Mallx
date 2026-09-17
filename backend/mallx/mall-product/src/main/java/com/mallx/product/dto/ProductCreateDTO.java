package com.mallx.product.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
public class ProductCreateDTO {
    @NotNull(message = "分类不能为null")
    private Long categoryId;
    private Long brandId;

    @NotBlank(message = "名称不能为空")
    @Size(max = 100,message = "商品名称不能超过100字")
    private String name;

    @Size(max = 200,message = "副标题不能超过200字")
    private String subtitle;

    private String description;

    private String mainImage;

    private Integer status;
}
