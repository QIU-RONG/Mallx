package com.mallx.payment.entity;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 支付记录（payments）
 *
 * <p>⚠️ 类名 {@code Payment} 反推出来的默认表名是 {@code payment}（少 s），
 * 而真实表名是 {@code payments} —— 必须显式写 {@code @TableName("payments")}，
 * 否则所有 SQL 报「表不存在」。与 {@code Inventory}/{@code Order} 是同一个坑。
 *
 * <p>⚠️ 本表没有 is_deleted 列 —— 禁止加 {@code @TableLogic}。
 *
 * <p>★★ 本表最容易看错的一点：{@code idx_payments_order_id} 是【普通索引，不是唯一索引】
 * —— 也就是说<b>一个订单允许挂多笔支付记录</b>。这不是设计漏洞，而是真实业务形态：
 * 支付失败重试、换支付方式、退款，都会在同一个 order_id 下留下多条记录。
 * ⇒ 因此「一笔订单只能成功支付一次」这条不变式<b>数据库管不了</b>
 * （不像 {@code payment_no} 有 UNIQUE 兜底），<b>只能靠订单状态机守住</b> —— 这正是 Day 13 的核心。
 *
 * <p>⚠️ {@code paidAt} 【不挂 fill】—— 它与 orders 的四个业务时间戳同类，
 * 由业务代码在成功那一刻手写，不是每次更新都刷。
 *
 * <p>约束：{@code payment_no} UNIQUE（{@code payments_payment_no_key}）；
 * 外键 {@code fk_payment_order → orders(id)}。
 */
@Data
@TableName("payments")
public class Payment {

    @TableId(type = IdType.AUTO)
    private Long id;

    /**
     * 支付流水号，UNIQUE —— 生成规则同订单号（前缀 + 时间 + 随机），撞号被数据库拦下（23505）。
     * ★ 它是并发安全之外的最后一道防线；但注意它<b>拦不住「同一订单付两次」</b>，
     * 因为两次生成的流水号一定不同。
     */
    private String paymentNo;

    private Long orderId;

    /**
     * 支付金额。
     * ⚠️ 永远取服务端 {@code orders.pay_amount}，<b>绝不接受客户端传值</b> —— 否则等于让顾客自己填付多少。
     */
    private BigDecimal amount;

    /** 支付方式，取值见 {@link com.mallx.payment.common.PaymentMethod}（列无 CHECK 约束） */
    private String method;

    /** 支付状态，取值见 {@link com.mallx.payment.common.PaymentStatus}（列无 CHECK 约束） */
    private String status;

    /** 支付完成时间（成功那一刻手写；失败/待支付时为 null） */
    private LocalDateTime paidAt;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;

    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedAt;
}
