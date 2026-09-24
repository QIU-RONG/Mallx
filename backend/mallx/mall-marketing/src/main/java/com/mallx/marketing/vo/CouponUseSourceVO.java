package com.mallx.marketing.vo;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 「这张券能不能用」的原始素材 —— <b>领取记录 + 券面原件</b>的合体（Day 21 新增）。
 *
 * <p>★ <b>它只做一件事：把判据和面额一次取回来。</b>
 * 由 {@code UserCouponMapper#selectForUse} 出参，进 {@code CouponServiceImpl#calcDiscount}
 * 之后被消费掉，<b>不会</b>出现在任何 HTTP 响应里 —— 它不是接口出参，
 * 所以字段是「数据库长什么样」而不是「前端想看什么」。
 *
 * <p>★★ <b>为什么需要一个新 VO，而不是复用 {@code UserCouponVO}</b>：
 * 「我的券」要展示「有效期至 X、满 100 减 20」，而下单算抵扣需要的是<b>判据</b> ——
 * {@code uc.status}（能不能用）、{@code c.status}（券有没有下架）、
 * {@code start_time / end_time}（在不在窗口内）。两者字段集有交集但不相等，
 * 硬塞进一个 VO 就会出现「有的字段只有某一条链路会用」的注释，那是分工没做对。
 *
 * <p>⚠️ 三处容易写错的地方：
 * <ol>
 *   <li><b>两个 {@code status} 是两回事</b>：{@link #status} 是
 *       {@code user_coupons.status}（这张券我用了没），{@link #couponStatus} 是
 *       {@code coupons.status}（这个券种下架没）。SQL 里必须<b>分别起别名</b>
 *       （{@code uc.status as status} / {@code c.status as coupon_status}），
 *       否则后者会被前者的名字盖掉 —— 而且<b>不报错</b>，只是判据变成另一个字段。</li>
 *   <li>{@link #expired} <b>不在表里</b>，由 SQL 现算（{@code c.end_time &lt; CURRENT_TIMESTAMP}）——
 *       与 {@code UserCouponVO} 同一个「惰性过期」口径，别在这里另立一套。</li>
 *   <li>{@code @NoArgsConstructor} 必须显式写 —— 它做 {@code resultType}，
 *       理由与 {@link CouponVO} / {@link UserCouponVO} 相同（反射无参构造 + setter）。</li>
 * </ol>
 *
 * <p>★★ <b>归属条件写在 SQL 里</b>（{@code WHERE uc.user_id = #{userId} AND uc.id = #{userCouponId}}），
 * 而 {@code userId} 来自 token 的 principal —— <b>绝不接收请求参数</b>。
 * ★ 这条同时是阶段二的 IDOR 防线：查不到 = 「不存在」与「不是你的」统一处理，
 * 不能让攻击者用别人的 {@code userCouponId} 试出「这个 id 有效」。
 */
@Data
@NoArgsConstructor
public class CouponUseSourceVO {

    /** 领取记录 id（{@code user_coupons.id}）—— 就是请求里传的那个 {@code userCouponId} */
    private Long userCouponId;

    /** 券种 id（{@code user_coupons.coupon_id}）—— 核销/退券不按它定位，只用于回显与断言 */
    private Long couponId;

    /** 券名（{@code coupons.name}）—— 报错文案要用（「『满100减20』已使用」比「券不可用」好得多） */
    private String couponName;

    /** {@code FIXED} / {@code DISCOUNT} —— 决定接下来用哪个公式算钱 */
    private String type;

    /** ★ 满减面额（{@code FIXED} 用）：券面原件，<b>不是</b>算出来的抵扣额 */
    private BigDecimal discountAmount;

    /** ★ 折扣系数（{@code DISCOUNT} 用）：券面原件，取值约定见 {@code calcDiscount} */
    private BigDecimal discountRate;

    /** 使用门槛：订单总额必须 ≥ 它才能用（可空 = 无门槛） */
    private BigDecimal minAmount;

    /** {@code user_coupons.status}：UNUSED 才可用 —— 见 {@code common/UserCouponStatus} */
    private String status;

    /** {@code coupons.status}：1 = 可领 / 0 = 下架 —— 下架的券不该再被消耗 */
    private Integer couponStatus;

    /** 券的生效起始时间 —— ★ 是 {@code calcDiscount} 的第 5 条判据（尚未开始 → 400），不是储备列 */
    private LocalDateTime startTime;

    /** 券的截止时间 */
    private LocalDateTime endTime;

    /** ★ 是否已过期 —— SQL 现算，不落库 */
    private Boolean expired;
}
