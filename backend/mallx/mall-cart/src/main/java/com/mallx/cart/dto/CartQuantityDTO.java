package com.mallx.cart.dto;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

/**
 * 修改购物车项数量（PUT /api/cart/{id}）
 *
 * <p>数量 &lt;= 0 直接 400 —— 想清空这一行走 DELETE 接口，不走这里改 0。
 */
@Data
public class CartQuantityDTO {

    @NotNull(message = "数量不能为空")
    @Min(value = 1, message = "数量至少为 1")
    private Integer quantity;
}
