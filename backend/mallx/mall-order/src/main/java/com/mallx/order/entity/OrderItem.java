package com.mallx.order.entity;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 订单明细（order_items）
 *
 * <p>★ 本表是【快照表】：{@code product_name / sku_name / price / image} 都是下单那一刻
 * 从 {@code product_skus / products} 拷过来的副本。商品后来改名、调价、软删，
 * 这里一个字都不变 —— 订单是「某个时间点的商业事实」，不许被后续的商品维护改口。
 *
 * <p>⚠️ {@code product_id / sku_id} 只是裸 BIGINT，故意不建外键 ——
 * 商品软删后订单还要能查得出来。
 *
 * <p>⚠️ 本表【只有 created_at，没有 updated_at】→ 只挂 INSERT，
 * 千万别写 INSERT_UPDATE（会生成对不存在列的赋值）。
 *
 * <p>外键 {@code fk_order_item_order → orders(id)}；索引 {@code idx_order_items_order_id}。
 */
@Data
@TableName("order_items")
public class OrderItem {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 所属订单 id（插入 orders 后从回填的 order.getId() 拿） */
    private Long orderId;

    private Long productId;

    private Long skuId;

    /** 商品名快照（NOT NULL） */
    private String productName;

    /** 规格名快照，可空 */
    private String skuName;

    /** ★ 下单时的单价快照 —— 不是实时价 */
    private BigDecimal price;

    private Integer quantity;

    /** price × quantity */
    private BigDecimal totalAmount;

    private String image;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;
}
