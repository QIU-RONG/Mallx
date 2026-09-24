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
 * 订单（orders）
 *
 * <p>⚠️ 类名 {@code Order} 反推出来的默认表名是 {@code order} —— 那是 SQL 保留字！
 * 漏了 {@code @TableName} 就会生成 {@code SELECT ... FROM order}，直接语法错误。
 * 必须显式写 {@code @TableName("orders")}。
 *
 * <p>⚠️ 本表没有 is_deleted 列 —— 禁止加 {@code @TableLogic}。
 *
 * <p>★ 收货信息是【快照】：存的是下单那一刻的姓名/电话/地址串，不是 {@code address_id}。
 * 用户事后改地址、删地址，历史订单不受影响。
 *
 * <p>⚠️ {@code paidAt / shippedAt / completedAt / cancelledAt} 四个业务时间戳
 * 【不挂 fill】—— 它们由业务代码在状态流转时手写，不是每次更新都刷。
 *
 * <p>约束：{@code order_no} UNIQUE（{@code orders_order_no_key}）；
 * 外键 {@code fk_order_user → users(id)}。
 * 索引 {@code idx_orders_user_id / idx_orders_status / idx_orders_created_at} 支持列表查询。
 */
@Data
@TableName("orders")
public class Order {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 订单号，UNIQUE —— 生成规则见 OrderServiceImpl#generateOrderNo，撞号会被数据库拦下（23505） */
    private String orderNo;

    private Long userId;

    /** 商品总额 */
    private BigDecimal totalAmount;

    /**
     * 实付金额。★ 恒等式：{@code payAmount = totalAmount - discountAmount}。
     * Day 12 建这列时注释写的是「V1.0 无优惠，= totalAmount」；
     * Day 21（优惠券阶段二）之后它才可能小于 {@code totalAmount}。
     */
    private BigDecimal payAmount;

    /**
     * 优惠额快照（列 {@code NUMERIC(12,2) NOT NULL DEFAULT 0}）—— Day 21 新增。
     *
     * <p>★ 不用券时是 <b>0，不是 null</b>：要区分「没用券」与「用了 0 元券」，
     * 这一列就必须在场。三列一起满足 {@code pay = total - discount}。
     *
     * <p>⚠️ 本列由 {@code backend/sql/11-order-discount.sql} 补上。
     * 漏跑补丁而实体已经有这个字段时，MP 生成的显式列清单会带上
     * {@code discount_amount} → 直接报「列不存在」（不是静默忽略）。
     * ★ 也就是说：<b>必须先落 DDL，再起应用</b>。
     */
    private BigDecimal discountAmount;

    /** 订单状态，取值见 {@link com.mallx.order.common.OrderStatus}（列无 CHECK 约束，全靠代码自觉） */
    private String status;

    // ---------------- 收货信息快照（下单时拷贝，之后永不变） ----------------

    private String receiverName;

    private String receiverPhone;

    /** 省市区 + 详址拼成一整串（表里就这么设计的，没有三个独立列） */
    private String receiverAddress;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;

    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedAt;

    // ---------------- 业务时间戳：不挂 fill，业务代码手写 ----------------

    private LocalDateTime paidAt;

    private LocalDateTime shippedAt;

    private LocalDateTime completedAt;

    private LocalDateTime cancelledAt;
}
