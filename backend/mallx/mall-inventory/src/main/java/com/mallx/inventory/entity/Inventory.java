package com.mallx.inventory.entity;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 库存（inventories）
 *
 * <p>⚠️ 类名 {@code Inventory} 反推出来的默认表名是 {@code inventory}（少 ies→y 的 s），
 * 必须显式写 {@code @TableName("inventories")}，否则所有 SQL 报「表不存在」。
 *
 * <p>⚠️ 本表没有 is_deleted 列 —— 禁止加 {@code @TableLogic}。
 *
 * <p>约束：{@code inventories_sku_id_key UNIQUE (sku_id)} → 一个 SKU 恰好一行库存。
 * 外键 {@code fk_inventory_sku → product_skus(id)}。
 *
 * <p>★ 恒等式（本表的核心不变式）：
 * <pre>
 *     total_stock = available_stock + locked_stock + sold_stock
 * </pre>
 * 含义：总库存 = 可售 + 已锁定（下单未付款）+ 已售出（已付款）。
 * 下单做的是 {@code available → locked}（锁定），支付时再做 {@code locked → sold}。
 * 任何一次扣减都必须保持这个等式 —— 冒烟里会专门断言。
 *
 * <p>⚠️ 列名带 stock 后缀：{@code total_stock} / {@code available_stock} /
 * {@code locked_stock} / {@code sold_stock}，驼峰映射自动对上，不要手动写 {@code @TableField}。
 */
@Data
@TableName("inventories")
public class Inventory {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long skuId;

    /** 总库存 = available + locked + sold（不变式） */
    private Integer totalStock;

    /** 可售库存（未售出且未被锁定） */
    private Integer availableStock;

    /** 锁定库存（已下单未付款） */
    private Integer lockedStock;

    /** 已售出（已付款） */
    private Integer soldStock;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;

    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedAt;
}
