package com.mallx.marketing.vo;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 优惠券出参 —— <b>管理端列表</b>与 <b>C 端可领列表</b>共用。
 *
 * <p>★ 共用的理由：两者的字段集完全一致（都是「这张券长什么样」），
 * 差别只在<b>筛选条件</b>（管理端能看下架的，C 端只能看可领的）—— 那是 WHERE 的事，
 * 不是 VO 的事。造两个一模一样的 VO 是纯负担。
 *
 * <p>⚠️ 本类有两处「必须显式写」的：
 * <ol>
 *   <li>{@code @NoArgsConstructor} —— 它被 MyBatis 当 {@code resultType} 用，
 *       走「反射无参构造 + setter」；只有 {@code @Data} 时通常也会生成无参构造，
 *       但<b>一旦有人加了 {@code @AllArgsConstructor} 就没了</b> → 运行才炸。
 *       显式写出来，把这条依赖钉死。</li>
 *   <li>别名一律下划线（那是 XML 侧的事）：{@code AS discount_amount} 而不是 {@code AS discountAmount}。
 *       ★ 注意这条规则的真正理由（Day 19 已实测修正）：不是因为「驼峰会静默 null」——
 *       MyBatis 查属性<b>大小写不敏感</b>，驼峰折小写后照样映射得上；
 *       而是因为下划线是<b>唯一在 {@code map-underscore-to-camel-case} 开关两态下都成立</b>的写法。</li>
 * </ol>
 *
 * <p>★ 刻意<b>不含</b> {@code received}（我有没有领过）这类「与我相关」的字段：
 * C 端列表是<b>公开</b>接口（匿名可访问），拿不到 userId → 放进来只能是 null，
 * 徒增困惑。「我领了什么」由 {@link UserCouponVO} 承担。这是分工，不是妥协。
 */
@Data
@NoArgsConstructor
public class CouponVO {

    private Long id;
    private String name;
    private String type;
    private BigDecimal discountAmount;
    private BigDecimal discountRate;
    private BigDecimal minAmount;
    private Integer totalCount;
    private Integer receivedCount;
    private LocalDateTime startTime;
    private LocalDateTime endTime;

    /** 1 = 可领 / 0 = 下架。C 端列表里恒为 1（SQL 已过滤），管理端才看得出差别 */
    private Integer status;
}
