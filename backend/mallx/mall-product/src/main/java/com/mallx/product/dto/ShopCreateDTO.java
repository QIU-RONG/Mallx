package com.mallx.product.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

/** 新建店铺（Day 64） */
@Data
public class ShopCreateDTO {

    @NotBlank(message = "店铺名不能为空")
    @Size(max = 100, message = "店铺名不能超过 100 字")
    private String name;

    @Size(max = 500, message = "logo 地址不能超过 500 字")
    private String logo;

    private String description;

    @Min(value = 0, message = "status 只能是 0 或 1")
    @Max(value = 1, message = "status 只能是 0 或 1")
    private Integer status;
}
