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

    private PaymentMethod() {
    }
}
