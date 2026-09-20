package com.mallx.review.vo;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.util.List;

/**
 * 商品评价列表的返回体（{@code GET /api/products/{productId}/reviews}）——
 * 分页四件套 <b>+ 两个聚合</b>。
 *
 * <p>★★ <b>为什么不复用 {@code PageResult&lt;T&gt;}</b>：
 * {@code PageResult} 是个<b>纯分页壳</b>（{@code records / total / current / size}），
 * 往里塞 {@code avgRating} 会让它变成「什么都能装的袋子」——
 * 之后每个业务都想往它身上挂点私货，最后没人说得清它到底装什么。
 * <b>聚合评分是「评价域」的概念，就让它在评价域的 VO 里。</b>
 * <p>★ 而 {@code GET /api/reviews/my} 没有聚合需求，<b>照旧复用 {@code PageResult}</b>
 * —— 该复用的复用，该分的分。
 *
 * <p>★ 两个聚合字段与 {@code records} <b>不是</b>「同一行数据的两半」：
 * {@code records} 只是<b>当前这一页</b>，而 {@code avgRating} / {@code reviewCount}
 * 是<b>整个商品</b>的统计（不过滤分页）—— 所以翻页时它们不变。
 *
 * <p>★★ 为什么不用 {@code products.rating} 这种冗余列：冗余靠「每次评价后重算」维护，
 * 一旦漏算就<b>永久漂移</b>（Day 14 已经花了一整个白天处理账目漂移）。
 * 实时 {@code AVG} 的值<b>必然等于</b>明细重算 ——「没有第二个真相」。
 *
 * <p>⚠️ 同样要 {@link NoArgsConstructor}：本类若被 MyBatis 当作 {@code resultType} 用，
 * 缺无参构造会抛 {@code ReflectionException}。
 */
@Data
@NoArgsConstructor
public class ReviewPageVO {

    /** 平均分，1 位小数；该商品一条评价都没有时为 0 */
    private BigDecimal avgRating;

    /** 该商品 {@code status = 1} 的评价总数（全量，不受分页影响） */
    private long reviewCount;

    /** 当前页的记录 */
    private List<ReviewVO> records;

    /** 总条数（MyBatis-Plus 的 count） */
    private long total;

    /** 当前页码 */
    private long current;

    /** 每页条数（夹紧后的值） */
    private long size;
}
