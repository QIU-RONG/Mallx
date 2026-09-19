package com.mallx.order.common;

/**
 * 订单状态常量（orders.status）
 *
 * <p>⚠️ 列是 {@code VARCHAR(30)} 且【无 CHECK 约束】—— 写错字符串数据库不会拦你，
 * 所以全项目必须只用这里的常量，禁止散落裸字符串（否则会出现
 * {@code "PENDING_PAYMENT"} 与 {@code "PENDING_PAY"} 共存这种数据灾难）。
 *
 * <p>状态流转（V1.0 只实现第一步）：
 * <pre>
 *   PENDING_PAYMENT --付款--> PAID --发货--> SHIPPED --确认--> COMPLETED
 *          \--取消/超时--> CANCELLED
 * </pre>
 */
public final class OrderStatus {

    /** 待付款（下单后的初始状态） */
    public static final String PENDING_PAYMENT = "PENDING_PAYMENT";

    /** 已付款（Day 13 支付模块流转：inventories.locked → sold） */
    public static final String PAID = "PAID";

    /** 已发货 */
    public static final String SHIPPED = "SHIPPED";

    /** 已完成 */
    public static final String COMPLETED = "COMPLETED";

    /** 已取消 */
    public static final String CANCELLED = "CANCELLED";

    private OrderStatus() {
    }
}
