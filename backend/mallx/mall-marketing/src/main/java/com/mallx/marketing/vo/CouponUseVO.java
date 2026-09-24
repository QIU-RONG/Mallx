package com.mallx.marketing.vo;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;

/**
 * 算完抵扣的<b>结论</b> —— {@code CouponService#calcDiscount} 的出参（Day 21 新增）。
 *
 * <p>★ 与 {@link CouponUseSourceVO} 的分工，是这一块最容易含混的地方：
 * <pre>
 *   CouponUseSourceVO  「券长什么样」—— 数据库的原始列，含判据与面额
 *   CouponUseVO        「这一单能减多少」—— 算完了的结论
 * </pre>
 * 前者会读出两个金额列（满减额 / 折扣系数），后者<b>只有一个</b>
 * {@link #deductionAmount}。两种券走两条公式，出口都是同一个数 ——
 * 这样下单链路就不需要再认识 {@code FIXED} / {@code DISCOUNT}。
 *
 * <p>★★ <b>字段名刻意不叫 {@code discountAmount}</b>：
 * 那个名字在 {@code coupons} 表里已经有主了（满减面额），
 * 而这里装的是「抵扣额」——折扣券算出来的值跟券面的 {@code discount_rate} 长得完全不一样。
 * 两个不同来源的钱共用一个名字，是金额计算链上最容易犯、也最难查的一类错。
 * ★ 到 {@code orders} 表落地时它对应列 {@code discount_amount}（见 {@code sql/11-order-discount.sql}），
 * 届时满足 {@code pay_amount = total_amount - discount_amount}。
 *
 * <p>★★ <b>{@code discount_rate} 的取值约定（本类必须钉住，因为列没有 CHECK 约束）</b>：
 * <pre>
 *   discount_rate 是【折扣系数 / 应付比例】，取值区间 (0, 1]
 *       0.80  → 打 8 折  → 抵扣额 = total × (1 - 0.80) = total × 0.20
 *       1.00  → 不打折   → 抵扣额 = 0
 * </pre>
 * 为什么必须<b>校验</b>而不是「照算」：中文里「折扣率」既能被读成「应付比例」
 * 也能被读成「减免比例」。若有人种了 {@code 80}（想表达 8 折），
 * 按本约定算出来是 {@code total × (1 - 80)} = <b>负数</b> —— 实付金额变负，
 * 一路错到支付接口才炸，而且炸得莫名其妙。
 * ⇒ {@code calcDiscount} 里要显式挡 {@code rate <= 0 || rate > 1}，
 * 让它在前台就变成一个 400 + 人话（「折扣率取值必须是 0 到 1 之间」），而不是一个负金额。
 */
@Data
@NoArgsConstructor
public class CouponUseVO {

    /** 领取记录 id —— 下游拿它去核销（{@code useCoupon} 的入参） */
    private Long userCouponId;

    /** 券种 id —— 只用于回显/断言，不参与任何定位 */
    private Long couponId;

    /** 券名 —— 报错与展示用 */
    private String couponName;

    /** ★★ 本单的实际抵扣额（元，2 位小数）。两种券型的统一出口 */
    private BigDecimal deductionAmount;
}
