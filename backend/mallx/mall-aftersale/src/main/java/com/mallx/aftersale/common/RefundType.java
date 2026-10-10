package com.mallx.aftersale.common;

import com.mallx.order.common.OrderStatus;

/**
 * 售后类型常量（refunds.type）—— Day 46。
 *
 * <p>⚠️ 列是 {@code VARCHAR(30)} 且【无 CHECK 约束】；合法取值只有这里两个。
 *
 * <p>★★★ <b>两个取值的分水岭是「货发出去了没有」</b> —— 这是售后域最硬的一条业务事实：
 * <pre>
 *   REFUND_ONLY    仅退款   货【没】发出去 ⇒ 没有实物要寄回 ⇒ 订单状态必须是 PAID
 *   RETURN_REFUND  退货退款 货【已】发出去 ⇒ 必须真的退回来  ⇒ 订单状态必须是 SHIPPED / COMPLETED
 * </pre>
 *
 * <p>★★ 为什么必须按订单状态卡死，而不是让用户自己选：
 * 「没收到货却申请退货退款」会让状态机走进一条<b>永远走不通</b>的路 ——
 * 买家拿不到物流单号可填（因为根本没有货），
 * 于是卡在 {@code APPROVED} 直到天荒地老，售后单变成僵尸单。
 * ★ 反过来「货已发出却申请仅退款」更糟：钱退了、货还在买家手里 ——
 * 那是<b>白送</b>，而且账面上看不出来（库存 {@code sold} 那格还挂着这批货）。
 *
 * <p>★ 这条校验写在 {@code RefundServiceImpl#apply}，不在 DTO 上：
 * 它要读订单状态才能判断，是<b>跨对象的关系校验</b>，
 * {@code @Valid} 表达不了（与 {@code CouponServiceImpl#createCoupon} 的两条关系校验同源）。
 */
public final class RefundType {

    /** 仅退款：不退货（订单未发货） */
    public static final String REFUND_ONLY = "REFUND_ONLY";

    /** 退货退款：要把货寄回来（订单已发货或已完成） */
    public static final String RETURN_REFUND = "RETURN_REFUND";

    private RefundType() {
    }

    /** 供 Service 做「类型是否合法」的判断；不含 null 检查（null 由 DTO 的 @NotBlank 挡） */
    public static boolean isValid(String type) {
        return REFUND_ONLY.equals(type) || RETURN_REFUND.equals(type);
    }

    /**
     * ★★ 该类型允许的订单状态起点 —— 上面那张表的代码版。
     *
     * <p>★ 故意引用 {@link OrderStatus} 的常量而不是裸字符串：
     * 「仅退款只认 PAID」这句话里，{@code PAID} 的定义权在<b>订单域</b>，
     * 这里只是引用。将来订单状态机改了，本文件会编译失败而不是静默放行。
     *
     * @param type     售后类型（已保证非 null）
     * @param orderStatus 订单当前状态
     * @return true = 这个订单状态可以申请这一类售后
     */
    public static boolean isOrderStatusAllowed(String type, String orderStatus) {
        if (REFUND_ONLY.equals(type)) {
            // 没发货 ⇒ 只能是「已付款」
            return OrderStatus.PAID.equals(orderStatus);
        }
        if (RETURN_REFUND.equals(type)) {
            // 已发货 ⇒ 在途中或已确认收货，都还能退
            return OrderStatus.SHIPPED.equals(orderStatus)
                    || OrderStatus.COMPLETED.equals(orderStatus);
        }
        return false;
    }

    /**
     * 给订单状态挑一个【说得清原因】的默认建议类型（用于报 400 时告诉用户该选哪个）。
     *
     * @return {@code REFUND_ONLY} / {@code RETURN_REFUND}；状态根本不能退款时返回 null
     */
    public static String suggestFor(String orderStatus) {
        if (OrderStatus.PAID.equals(orderStatus)) {
            return REFUND_ONLY;
        }
        if (OrderStatus.SHIPPED.equals(orderStatus) || OrderStatus.COMPLETED.equals(orderStatus)) {
            return RETURN_REFUND;
        }
        return null;
    }
}
