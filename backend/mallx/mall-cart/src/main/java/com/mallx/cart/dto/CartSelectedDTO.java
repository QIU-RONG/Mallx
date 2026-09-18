package com.mallx.cart.dto;

import jakarta.validation.constraints.NotNull;
import lombok.Data;

/**
 * 勾选 / 取消勾选购物车项（PUT /api/cart/{id}/selected）
 */
@Data
public class CartSelectedDTO {

    @NotNull(message = "selected 不能为空")
    private Boolean selected;
}
