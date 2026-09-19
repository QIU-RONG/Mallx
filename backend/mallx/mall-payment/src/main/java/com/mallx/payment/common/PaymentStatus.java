package com.mallx.payment.common;

/**
 * 支付状态常量（payments.status）
 *
 * <p>⚠️ 列是 {@code VARCHAR} 且【无 CHECK 约束】—— 写错字符串数据库不会拦你。
 * 全项目必须只用这里的常量，禁止散落裸字符串（否则会出现
 * {@code "SUCCESS"} 与 {@code "SUCCEED"} 共存这种数据灾难）。
 *
 * <p>V1.0 是「模拟支付」：调用即同步成功，所以线上只会写入 {@link #SUCCESS}。
 * 另外两个是留给真实网关（异步回调、失败重试、退款）的占位 —— 现在定义了但不用，
 * 免得将来各处自己造字符串。
 */
public final class PaymentStatus {

    /** 支付成功（V1.0 唯一会被写入的值） */
    public static final String SUCCESS = "SUCCESS";

    /** 支付失败（真实网关回调才会产生，V1.0 不用） */
    public static final String FAILED = "FAILED";

    /** 已退款（V1.0 不用） */
    public static final String REFUNDED = "REFUNDED";

    private PaymentStatus() {
    }
}
