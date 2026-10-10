package com.mallx.payment.common;

/**
 * 支付方式常量（payments.method）
 *
 * <p>⚠️ 列是 {@code VARCHAR} 且【无 CHECK 约束】—— 校验只能靠代码。
 * Day 13 的 {@code PaymentCreateDTO} 用 {@code @Pattern} 把取值锁在这三个之内，
 * Service 侧再兜一层白名单，避免脏值落库。
 *
 * <p>V1.0 是模拟支付：选了方式就直接成功，不真正调用任何网关。
 * 但<b>接口形状按真实业务设计</b> —— 将来把 {@code PaymentServiceImpl} 里
 * 「直接成功」换成「调用网关 + 等回调」，上层代码一行都不用改。
 */
public final class PaymentMethod {

    /** 支付宝 */
    public static final String ALIPAY = "ALIPAY";

    /** 微信支付 */
    public static final String WECHAT = "WECHAT";

    /** 余额支付 */
    public static final String BALANCE = "BALANCE";

    /**
     * ★ 退款（Day 46）—— <b>不是一种「支付方式」，而是负向流水的标记</b>。
     *
     * <p>退款没有「用户选了哪种方式付」这回事（钱是按原路退回的），
     * 所以严格说它不该与 {@link #ALIPAY} / {@link #WECHAT} / {@link #BALANCE} 并列。
     * ★ 但 {@code payments.method} 是 {@code NOT NULL} 且无 CHECK 约束，
     * 必须给个值 —— 而<b>给一个专门的值</b>比「沿用原支付方式」清晰得多：
     * 后者会让「按支付方式统计」把退款那笔算进支付宝的成交额里。
     *
     * <p>⚠️ 判据：要查「这单真正付成功过几次」，条件是
     * {@code status = 'SUCCESS' AND method <> 'REFUND'}，
     * 只看 {@code status} 是不够的（退款流的 status 是 {@code REFUNDED}，本来就不同，
     * 但多一层显式条件就能防住将来有人给退款也写 {@code SUCCESS}）。
     */
    public static final String REFUND = "REFUND";

    private PaymentMethod() {
    }
}
