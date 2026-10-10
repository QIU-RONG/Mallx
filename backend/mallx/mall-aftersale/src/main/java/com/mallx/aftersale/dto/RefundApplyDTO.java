package com.mallx.aftersale.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 申请退款（C 端）—— {@code POST /api/refunds} 的请求体（Day 46）。
 *
 * <p>★ 只有三个字段，而且<b>没有金额</b>：
 * 退款额<b>只可能</b>来自服务端读出的 {@code orders.pay_amount}。
 * 让客户端传「我要退多少钱」等于让顾客自己定价 ——
 * 那是本项目在支付侧就已经定下的底线（{@code Payment#amount} 的注释写得比这里更狠）。
 *
 * <p>★★ <b>本 DTO 做不到的那条关键校验</b>：「这个 type 与订单当前状态是否匹配」。
 * 它要读订单才知道，属<b>跨对象的关系校验</b>，{@code @Valid} 表达不了
 * ⇒ 放在 {@code RefundServiceImpl#apply} 里守
 * （与 {@code CouponCreateDTO} 那两条「类型 ↔ 金额字段」完全同源）。
 *
 * <p>⚠️ 字段注释里那句「取值范围」只是给人看的 ——
 * 列上没有 CHECK 约束，真正的守门是 {@code @Pattern} + Service 白名单两层。
 */
@Data
public class RefundApplyDTO {

    /** 要退的订单 id（★ 归属由 Service 侧 SQL 校验，这里只管非空） */
    @NotNull(message = "订单 id 不能为空")
    private Long orderId;

    /**
     * 售后类型：{@code REFUND_ONLY} / {@code RETURN_REFUND}。
     *
     * <p>★ 用 {@code @Pattern} 把取值集合锁在参数层 ——
     * 「合法取值有哪些」是<b>参数层就能说清</b>的事实，不该拖到业务层
     * （与 {@code CouponCreateDTO#type} 同一条分层判据）。
     */
    @NotBlank(message = "售后类型不能为空")
    @Pattern(regexp = "REFUND_ONLY|RETURN_REFUND",
             message = "售后类型只能是 REFUND_ONLY（仅退款）或 RETURN_REFUND（退货退款）")
    private String type;

    /** 退款原因（买家填，落库供运营/纠纷时查） */
    @NotBlank(message = "退款原因不能为空")
    @Size(max = 200, message = "退款原因不能超过 200 字")
    private String reason;
}
