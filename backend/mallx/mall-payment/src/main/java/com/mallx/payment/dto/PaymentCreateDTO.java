package com.mallx.payment.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import lombok.Data;

/**
 * 支付入参（POST /api/payments）
 *
 * <p>★ 只有 {@code orderId} + {@code method}，<b>故意没有 amount</b> ——
 * 金额的唯一来源是服务端 {@code orders.pay_amount}。
 * 请求体里出现金额字段，等于让顾客自己填「我付多少」。
 *
 * <p>★ {@code @Pattern} 的正则<b>不带 {@code ^...$}</b>：Bean Validation 用
 * {@code Matcher.matches()} 匹配，本身就是「整串相等」语义，加了锚点只是冗余。
 * <p>⚠️ 但 {@code @Pattern} 认为 {@code null} 是合法的 → 必须再配一个 {@code @NotBlank}
 * 才能拦住 null 与空串，两个注解缺一不可。
 *
 * <p>★ {@code orderId} 走 body 而不是路径 —— 支付的是「哪个订单」是资源标识，
 * 而「谁在付」永远只从 token 来（见 {@code PaymentController}），两者不放在一起。
 */
@Data
public class PaymentCreateDTO {

    @NotNull(message = "订单 id 不能为空")
    private Long orderId;

    @NotBlank(message = "支付方式不能为空")
    @Pattern(regexp = "ALIPAY|WECHAT|BALANCE", message = "支付方式不正确")
    private String method;
}
