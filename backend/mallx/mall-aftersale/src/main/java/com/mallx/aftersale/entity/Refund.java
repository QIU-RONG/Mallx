package com.mallx.aftersale.entity;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 退款 / 售后单（refunds）—— Day 46，<b>全项目第 25 张表</b>。
 *
 * <p>★ 表名没有复数陷阱（{@code refunds} 不是保留字），但
 * {@code @TableName} 仍然显式写 —— 与 {@code Order} / {@code Inventory} 同一条规矩：
 * <b>靠约定不如靠声明</b>，将来谁改了表名这里会立刻编译期可见。
 *
 * <p>⚠️ 本表没有 {@code is_deleted} 列 —— <b>禁止加 {@code @TableLogic}</b>。
 * 售后记录是<b>凭证</b>，删掉它等于销毁证据（与 {@code payments} / {@code inventory_logs} 同理）。
 *
 * <p>★★ {@code amount} 是<b>快照</b>：申请那一刻的 {@code orders.pay_amount}。
 * 留成列而不是「用的时候现查订单」，是为了让「这单退了多少钱」成为一个<b>已发生的事实</b>
 * —— 订单金额事后被改，也不该改写已经退出去的那笔钱。
 *
 * <p>⚠️ 五个业务时间戳（{@code appliedAt} … {@code refundedAt}）
 * <b>一律不挂 fill</b> —— 与 {@code orders} 的四个时间戳同理由：
 * 它们记的是「业务事实发生的那一刻」，不是「这一行被改过」。
 * ★ 也正因如此，「审核通过有没有写 audited_at」本身就是一条可断言的判据。
 *
 * <p>约束：{@code refund_no} UNIQUE；
 * 外键 {@code fk_refund_order → orders(id)}、{@code fk_refund_user → users(id)}；
 * ★★ 部分唯一索引 {@code uk_refunds_active_order}
 * —— 一张订单最多一张【进行中】的售后单（详见 {@code backend/sql/17-refunds.sql}）。
 */
@Data
@TableName("refunds")
public class Refund {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 退款单号，UNIQUE —— 生成规则同订单号（前缀 RFD + 时间 + 随机） */
    private String refundNo;

    private Long orderId;

    private Long userId;

    /** 售后类型：REFUND_ONLY / RETURN_REFUND，取值见 {@link com.mallx.aftersale.common.RefundType} */
    private String type;

    /** 状态，取值见 {@link com.mallx.aftersale.common.RefundStatus}（列无 CHECK 约束） */
    private String status;

    /** ★ 退款额快照（= 申请时 orders.pay_amount）。V1.0 只支持全额退款 */
    private BigDecimal amount;

    /** 买家填写的退款原因 */
    private String reason;

    /** 管理端审核备注（拒绝原因等） */
    private String remark;

    /** 退货物流单号（仅 RETURN_REFUND 用，买家寄出时填） */
    private String trackingNo;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;

    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedAt;

    // ---------------- 业务时间戳：不挂 fill，业务代码手写 ----------------

    private LocalDateTime appliedAt;

    private LocalDateTime auditedAt;

    private LocalDateTime shippedAt;

    private LocalDateTime receivedAt;

    private LocalDateTime refundedAt;
}
