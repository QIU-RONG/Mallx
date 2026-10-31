package com.mallx.product.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.Data;

import java.util.List;

/** 批量上下架（Day 91）：一次最多 100 个，status 只允许 0/1 */
@Data
public class BatchProductStatusDTO {

    @NotEmpty(message = "商品 id 不能为空")
    @Size(max = 100, message = "一次最多 100 个商品")
    private List<Long> ids;

    @NotNull(message = "status 不能为空")
    @Min(value = 0, message = "status 只能是 0/1")
    @Max(value = 1, message = "status 只能是 0/1")
    private Integer status;
}
