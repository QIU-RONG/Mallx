package com.mallx.payment.vo;

import lombok.AllArgsConstructor;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 支付结果（POST /api/payments 的 data）
 *
 * <p>★ 带上 {@code orderNo} 方便前端直接展示「哪张订单付掉了」，不必再查一次订单接口。
 * <p>★ 刻意【不带 userId】—— 内部归属字段不外泄（同 {@code OrderVO} / {@code AddressVO} 的规矩）。
 *
 * <p>⚠️ {@code @AllArgsConstructor} 的参数顺序 = <b>字段声明顺序</b>；
 * 且一旦有它，Lombok 就<b>不再生成无参构造</b> → 不能 {@code new PaymentVO()} 再 setter。
 * <p>⚠️ 还要注意字段类型：{@code orderId} 是 Long、{@code amount} 是 BigDecimal，
 * 相邻的 {@code paymentNo} / {@code orderNo} 都是 String —— 顺序写错编译器<b>不会</b>报错，
 * 值会悄悄串位。构造时对着字段表核一遍。
 */
@Data
@AllArgsConstructor
public class PaymentVO {

    private Long id;

    /** 支付流水号（PAY + 时间 + 随机）*/
    private String paymentNo;

    private Long orderId;

    /** 订单号快照 —— 让前端一眼看清「付的是哪张单」*/
    private String orderNo;

    private BigDecimal amount;

    /** ALIPAY / WECHAT / BALANCE */
    private String method;

    /** V1.0 只会是 SUCCESS */
    private String status;

    private LocalDateTime paidAt;
}
