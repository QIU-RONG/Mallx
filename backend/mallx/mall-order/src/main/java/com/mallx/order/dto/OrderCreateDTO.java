package com.mallx.order.dto;

import jakarta.validation.constraints.NotNull;
import lombok.Data;

/**
 * 下单入参（POST /api/orders）
 *
 * <p>★ 只有 {@code addressId}，没有 skuIds / quantity：
 * 买什么、买几件，唯一来源是「购物车里 {@code selected = TRUE} 的行」，
 * 客户端只表达「用哪个地址」—— 少一个可以被伪造的输入面。
 *
 * <p>为什么传 id 而不是收货信息：地址是用户维护的独立资源，下单时按 id 引用、
 * 把内容【拷贝成快照】存进 orders（并校验归属，防 IDOR）。
 */
@Data
public class OrderCreateDTO {

    @NotNull(message = "收货地址不能为空")
    private Long addressId;

    /**
     * 要使用的优惠券（可选）—— 指向 {@code user_coupons.id}。
     *
     * <p>★★ <b>为什么是 {@code user_coupons.id} 而不是 {@code coupons.id}</b>：
     * 「用哪张券」的含义是「用<b>我领到的那一张</b>」，不是「用那个券的定义」。
     * 传 {@code coupon_id} 的话服务端还得猜是哪一次领取 —— 而
     * {@code user_coupons} 才是「券 ↔ 人」的绑定：{@code status} /
     * {@code order_id} / {@code used_at} 都挂在那张表上。
     *
     * <p>★★ <b>可空</b>：{@code null} = 不用券 ⇒ 下单必须走【原路】，
     * 金额与 Day 12 完全一致。这是阶段二最硬的一条兼容约束 ——
     * M1 回归（198 条）跑的就是真实下单链路（day14/15/16 三个 E2E），
     * 它们都不传这个字段，所以这一行必须让老行为一个字节都不变。
     *
     * <p>⚠️ <b>归属校验在服务端</b>：本字段只表达「想用哪张」，
     * 不表达「能不能用」。把别人的券 id 传进来必须被拒（伪装 404 / 400），
     * 绝不能因为「传了就能用」而越权 —— 与 {@link #addressId} 同一套 IDOR 口径。
     */
    private Long userCouponId;
}
