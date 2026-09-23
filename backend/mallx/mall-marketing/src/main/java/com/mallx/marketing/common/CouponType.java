package com.mallx.marketing.common;

/**
 * 优惠券类型常量 —— 与 {@code com.mallx.order.common.OrderStatus} 同一种做法。
 *
 * <p>★ 为什么需要它：{@code coupons.type} 列是 {@code VARCHAR(30)}，<b>没有 CHECK 约束</b>
 * （见 01-schema.sql:285）。取值写错了 DB 一声不吭 —— 所以「合法的取值集合」只能
 * 由应用层表达，并且把它写成常量而不是散落的字符串字面量。
 *
 * <p>★ 两个取值各自依赖一个字段，且<b>互斥</b>（这是业务规则，DB 管不了）：
 * <pre>
 *   FIXED    （满减）→ 必须有 discount_amount，不看 discount_rate
 *   DISCOUNT （折扣）→ 必须有 discount_rate，  不看 discount_amount
 * </pre>
 * 这条规则由 {@code CouponServiceImpl.createCoupon} 守。
 * ★ 别试图用「都填上就没事」绕过：一张券同时有「减 20」和「打 8 折」，
 * 下单时到底按哪个算？—— 歧义本身就是要拒绝的理由。
 */
public final class CouponType {

    /** 满减券：直接减 {@code discount_amount} 元 */
    public static final String FIXED = "FIXED";

    /** 折扣券：按 {@code discount_rate} 打折 */
    public static final String DISCOUNT = "DISCOUNT";

    private CouponType() {
    }

    /** 供 Service 做「类型是否合法」的判断；不含 null 检查（null 由 @NotBlank 挡在参数层） */
    public static boolean isValid(String type) {
        return FIXED.equals(type) || DISCOUNT.equals(type);
    }
}
