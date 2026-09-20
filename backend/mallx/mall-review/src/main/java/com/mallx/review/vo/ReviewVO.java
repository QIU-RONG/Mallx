package com.mallx.review.vo;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

/**
 * 一条评价（{@code POST /api/reviews} 的返回、商品评价列表的行、我的评价列表的行）
 *
 * <p>★ 一处定义、多处复用：三处的字段集完全一致，所以 XML 的 {@code resultType}
 * 直接指向本类 —— 不另建 VO（与 {@code PaymentVO} 同一个做法）。
 *
 * <p>★ 商品信息（{@link #productName} / {@link #skuName} / {@link #image}）
 * 全部来自 {@code order_items} 的<b>快照列</b>，不是回 {@code products} 查的 ——
 * 这也是 {@code mall-review} 不需要依赖 {@code mall-product} 的原因。
 *
 * <p>★★ {@code userId} <b>刻意不在这里</b>：内部归属字段不外泄
 * （同 {@code OrderVO} / {@code AddressVO} / {@code PaymentVO} 的规矩）。
 * 要展示「谁评的」就只用 {@link #userNickname}，且昵称为空时由 SQL 兜底成固定串
 * —— 客户端拿到的任何字段都不足以反推用户 id。
 *
 * <p>⚠️ 必须挂 {@link NoArgsConstructor}：MyBatis 的 {@code resultType} 映射走的是
 * 「<b>反射无参构造 + setter 赋值</b>」，缺了它会在 {@code DefaultObjectFactory.create()}
 * 抛 {@code ReflectionException} —— <b>编译通过、启动成功，直到真去查一次才炸</b>
 * （Day 13 在 {@code PaymentVO} 上实际踩过）。
 */
@Data
@NoArgsConstructor
public class ReviewVO {

    /** 评价 id */
    private Long id;

    /** ★ 这条评价挂在哪条订单明细上（一明细一评，唯一约束保证） */
    private Long orderItemId;

    private Long productId;

    /** 商品名快照（来自 order_items，下单那一刻的值） */
    private String productName;

    /** 规格名快照 */
    private String skuName;

    /** 主图快照 */
    private String image;

    /** 评分 1..5 */
    private Integer rating;

    /** 评价内容（可空） */
    private String content;

    /**
     * 评价人昵称（{@code LEFT JOIN users}）。
     * ★ SQL 里用 {@code COALESCE(u.nickname, '用户****')} 兜底 —— 匿名的评价也得有个显示名。
     */
    private String userNickname;

    private LocalDateTime createdAt;
}
