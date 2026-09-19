package com.mallx.payment.vo;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 支付记录（`POST /api/payments` 的返回、`GET /api/payments` 的列表行、`GET /api/payments/{id}` 的详情）
 *
 * <p>★ 带上 {@code orderNo} 方便前端直接展示「哪张订单付掉了」，不必再查一次订单接口。
 * <p>★ 刻意【不带 userId】—— 内部归属字段不外泄（同 {@code OrderVO} / {@code AddressVO} 的规矩）。
 *
 * <p>★★ 本类一处定义、三处复用：① 支付成功的返回；② 我的支付记录列表；③ 支付记录详情。
 * 三者字段集完全一致，所以第 4 步的 XML {@code resultType} 直接指向本类 —— 不另建 VO。
 *
 * <p>⚠️ {@code @AllArgsConstructor} 的参数顺序 = <b>字段声明顺序</b>；
 * 且一旦有它，Lombok 就<b>不再生成无参构造</b>。
 *
 * <p>★★ 但 MyBatis 的 {@code resultType} 映射走的是「<b>反射无参构造 + setter 赋值</b>」——
 * 没有无参构造会在 {@code DefaultObjectFactory.create()} 里抛
 * {@code ReflectionException: Error instantiating class ...}。
 * ⇒ 所以本类<b>必须同时挂 {@code @NoArgsConstructor}</b>（Day 13 第 4 步补的），
 * 两个注解共存后 {@code new PaymentVO(全参)} 与 {@code new PaymentVO()} 都能用。
 * ⚠️ 这个错<b>编译期不报</b>：接口能编译、应用能启动，直到真去查一次列表才炸。
 *
 * <p>⚠️ 还要注意字段类型：{@code orderId} 是 Long、{@code amount} 是 BigDecimal，
 * 相邻的 {@code paymentNo} / {@code orderNo} 都是 String —— 顺序写错编译器<b>不会</b>报错，
 * 值会悄悄串位。构造时对着字段表核一遍。
 */
@Data
@NoArgsConstructor
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
