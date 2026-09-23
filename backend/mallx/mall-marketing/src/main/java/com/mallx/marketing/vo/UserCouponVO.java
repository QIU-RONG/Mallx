package com.mallx.marketing.vo;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 我的优惠券出参 —— {@code GET /api/coupons/my}。
 *
 * <p>★ 它是「领取记录 + 券面快照」的<b>合体</b>：前者来自 {@code user_coupons}，
 * 后者来自 {@code coupons}。用户在「我的券」页面要看到的是「满 100 减 20，有效期至 X」，
 * 而不是一个 {@code coupon_id}。
 *
 * <p>★★ 三处值得注意：
 * <ol>
 *   <li>{@link #expired} —— <b>不在表里</b>，由 SQL 算出来
 *       （{@code c.end_time < CURRENT_TIMESTAMP}）。
 *       ★ 同时要断言「DB 里 {@code user_coupons.status} 仍然是 {@code 'UNUSED'}」——
 *       这正是「惰性过期」的<b>反证</b>：查询时算，不写回。
 *       若某天引入定时任务把它落库，那条断言必须同步改（否则它会一直绿，却不再证明任何事）。</li>
 *   <li>{@link #orderId} / {@link #usedAt} —— 阶段二的字段，本日恒为 null。
 *       留着它们是为了让列表在前端「已使用」页签里拿得到数据，不必再改一次 VO。</li>
 *   <li>{@code @NoArgsConstructor} 必须显式写 —— 它做 {@code resultType}，理由同 {@link CouponVO}。</li>
 * </ol>
 *
 * <p>★★ <b>归属过滤写在 SQL 里</b>（{@code WHERE uc.user_id = #{userId}}），
 * 而 {@code userId} 来自 token 的 principal —— <b>绝不接收请求参数</b>。
 * 这条是本项目自 Day 11 起的一贯做法（C 端「查谁的」只能由登录态决定）。
 * ★ 验收会用 IDOR 手法验它：拿 A 的 token 打 {@code /api/coupons/my}，
 * 结果里不能出现 B 的券 —— 且光看状态码证明不了，要核 DB。
 */
@Data
@NoArgsConstructor
public class UserCouponVO {

    /** 领取记录 id（{@code user_coupons.id}） */
    private Long id;

    private Long couponId;
    private String couponName;
    private String type;

    /** 券面信息快照（本日实时 JOIN 取，不是快照列 —— 阶段二若要「领取时的面额」才需落库） */
    private BigDecimal discountAmount;
    private BigDecimal discountRate;
    private BigDecimal minAmount;

    /** {@code UNUSED} / {@code USED} / {@code EXPIRED} —— 本日只会是 UNUSED */
    private String status;

    private LocalDateTime receivedAt;

    /** 阶段二写 */
    private LocalDateTime usedAt;

    /** 阶段二写 */
    private Long orderId;

    /** 券的截止时间（展示用，「有效期至 X」） */
    private LocalDateTime endTime;

    /** ★ 是否已过期 —— 由 SQL 计算，不落库 */
    private Boolean expired;
}
