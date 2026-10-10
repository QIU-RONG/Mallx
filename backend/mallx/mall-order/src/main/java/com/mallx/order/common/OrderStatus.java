package com.mallx.order.common;

/**
 * 订单状态常量（orders.status）
 *
 * <p>⚠️ 列是 {@code VARCHAR(30)} 且【无 CHECK 约束】—— 写错字符串数据库不会拦你，
 * 所以全项目必须只用这里的常量，禁止散落裸字符串（否则会出现
 * {@code "PENDING_PAYMENT"} 与 {@code "PENDING_PAY"} 共存这种数据灾难）。
 *
 * <p>状态流转：
 * <pre>
 *   PENDING_PAYMENT --付款--> PAID --发货--> SHIPPED --确认--> COMPLETED
 *          \--取消/超时--> CANCELLED
 *
 *   ★ Day 46 新增：PAID / SHIPPED / COMPLETED --全额退款--> REFUNDED（终态）
 * </pre>
 *
 * <p>★★ {@code REFUNDED} 是 Day 46 加的<b>第二条终态</b>（另一条是 {@code CANCELLED}）。
 * 两条终态的语义完全不同，别混：
 * <pre>
 *   CANCELLED   钱没收过（或已原路退回）：货从 locked 回 available
 *   REFUNDED    钱收过又退出去了    ：货从 sold   回 available
 * </pre>
 * 「付没付过钱」是唯一分岔点 —— 它决定回补库存走 {@code releaseLocked} 还是
 * {@code returnToStock}，走错一个守卫就 0 行、整笔回滚。
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

    /** 已取消（未支付就终止）—— 终态 */
    public static final String CANCELLED = "CANCELLED";

    /**
     * ★ 已退款（Day 46）—— <b>第二条终态</b>：钱收过、又全退了。
     *
     * <p>与 {@link #CANCELLED} 的分岔点是「付没付过钱」：
     * {@code CANCELLED} 的货还在 {@code locked} 格子里（回补走 {@code releaseLocked}），
     * {@code REFUNDED} 的货已经在 {@code sold} 格子里（回补走 {@code returnToStock}）。
     *
     * <p>⚠️ 本状态是<b>终态</b>：不允许再发货、再确认收货，也不允许再申请退款
     * （{@code markRefunded} 的 CAS 起点集合里没有它，重复退款会被 0 行挡下）。
     */
    public static final String REFUNDED = "REFUNDED";

    private OrderStatus() {
    }
}
