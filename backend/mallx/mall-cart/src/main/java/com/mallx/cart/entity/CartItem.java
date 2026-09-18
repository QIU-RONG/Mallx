package com.mallx.cart.entity;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 购物车行（cart_items）
 *
 * <p>⚠️ 本表没有 is_deleted 列 —— 禁止加 {@code @TableLogic}：
 * 加了会让 MP 给所有查询拼上 {@code AND is_deleted = 0}，直接报「列不存在」，
 * 且该表所有接口全挂。购物车是临时数据，删了就删了，不需要软删除。
 *
 * <p>约束：{@code uk_cart_user_sku UNIQUE (user_id, sku_id)}
 * → 同一用户 + 同一 SKU 只能有一行，重复加购必须「合并数量」而非「插新行」。
 */
@Data
@TableName("cart_items")
public class CartItem {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long userId;

    private Long skuId;

    private Integer quantity;

    private Boolean selected;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;

    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedAt;
}
