package com.mallx.aftersale.common;

/**
 * 退款单状态常量（refunds.status）—— Day 46。
 *
 * <p>⚠️ 列是 {@code VARCHAR(30)} 且【无 CHECK 约束】（与 {@code OrderStatus} 同一个理由）：
 * 写错字符串数据库不会拦你，所以全项目必须只用这里的常量，禁止散落裸字符串。
 *
 * <p>★★★ <b>状态机（两种售后类型走不同的路径，唯一差别在「有没有实物要寄回」）</b>：
 * <pre>
 *   仅退款 REFUND_ONLY（订单还没发货 ⇒ 没有实物要寄回）
 *     APPLIED ─审核通过─▶ APPROVED ─执行退款─▶ SUCCESS
 *        │                                       │
 *        ├─审核拒绝─▶ REJECTED（终）             └─（终）
 *        └─用户撤销─▶ CANCELLED（终）
 *
 *   退货退款 RETURN_REFUND（订单已发货 ⇒ 货要真的寄回来）
 *     APPLIED ─审核通过─▶ APPROVED ─买家填物流单号─▶ RETURNING
 *        │                                            │
 *        ├─审核拒绝─▶ REJECTED（终）      卖家确认收货└─▶ REFUNDING ─执行退款─▶ SUCCESS（终）
 *        └─用户撤销─▶ CANCELLED（终）
 * </pre>
 *
 * <p>★★ <b>为什么 RETURN_REFUND 比 REFUND_ONLY 多两段</b>：
 * 多出来的 {@code RETURNING} / {@code REFUNDING} 不是装饰，它们各自对应一个
 * <b>必须由不同角色完成、且跨越时间的动作</b>：
 * <pre>
 *   RETURNING  买家把货交给物流（外部世界的事，系统只能等）
 *   REFUNDING  卖家收到货、确认无误（同样是外部世界的事）
 * </pre>
 * 把它们压进 {@code APPROVED} 一个状态里，就没法回答
 * 「货寄出了没」「卖家收到了没」这两个售后纠纷里最常被问的问题。
 *
 * <p>★★★ <b>三个终态，且只有 {@link #SUCCESS} 会动钱</b>：
 * <pre>
 *   SUCCESS    钱退了、货回了、券退了、订单置 REFUNDED
 *   REJECTED   审核没过 —— 一分钱没动
 *   CANCELLED  买家自己撤了 —— 一分钱没动
 * </pre>
 * ★ 判据：退款动作<b>只挂在 {@code → SUCCESS} 这一条边上</b>，
 *   全项目只有一处代码会调用「执行退款」那五个写点。
 *
 * <p>⚠️ {@code REFUNDING} 与 {@link #SUCCESS} 只差一步，但含义完全不同：
 * {@code REFUNDING} = 卖家已收货、<b>钱还没退</b>；{@code SUCCESS} = 钱已退。
 * 把「已收货」当成「已退款」，就会出现「用户没收到钱、系统却显示售后已完成」。
 */
public final class RefundStatus {

    /** 已申请，待审核（初始状态） */
    public static final String APPLIED = "APPLIED";

    /** 审核通过。★ REFUND_ONLY 可直接执行退款；RETURN_REFUND 还要等买家寄回 */
    public static final String APPROVED = "APPROVED";

    /** 审核被拒 —— 终态，一分钱没动 */
    public static final String REJECTED = "REJECTED";

    /** 买家已寄出（仅 RETURN_REFUND；{@code tracking_no} 必填） */
    public static final String RETURNING = "RETURNING";

    /** 卖家已确认收货，待执行退款（仅 RETURN_REFUND） */
    public static final String REFUNDING = "REFUNDING";

    /** 退款已完成 —— 终态，★ 唯一会动钱的那个状态 */
    public static final String SUCCESS = "SUCCESS";

    /** 买家撤销申请 —— 终态，一分钱没动 */
    public static final String CANCELLED = "CANCELLED";

    private RefundStatus() {
    }

    /**
     * 是否【进行中】—— 与 DB 上的部分唯一索引
     * {@code uk_refunds_active_order} 的 {@code WHERE} 子集<b>逐字一致</b>。
     *
     * <p>★ 这个方法存在的唯一理由就是那条索引：Java 侧判断「有没有进行中的售后单」
     * 与数据库侧判断「能不能再插一张」必须用<b>同一个集合</b>。
     * ⚠️ 两边一旦漂移（比如这里忘了加 {@code REFUNDING}），
     * 就会出现「Service 说没有、可以插」→「数据库说已存在、23505」的 500。
     */
    public static boolean isActive(String status) {
        return APPLIED.equals(status)
                || APPROVED.equals(status)
                || RETURNING.equals(status)
                || REFUNDING.equals(status);
    }

    /** 是否终态（终态之后不能再推进） */
    public static boolean isTerminal(String status) {
        return REJECTED.equals(status) || SUCCESS.equals(status) || CANCELLED.equals(status);
    }
}
