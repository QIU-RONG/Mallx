package com.mallx.review.vo;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

/**
 * 管理端评价行（{@code GET /api/admin/reviews}，Day 55）。
 *
 * <p>★★ <b>为什么另建一个 VO，而不是给 {@code ReviewVO} 加一个 {@code status} 字段</b>：
 * <ul>
 *   <li>{@code ReviewVO} 同时是 <b>C 端公开接口</b>（{@code GET /api/products/{id}/reviews}）
 *       的出参。往里加字段 = 改变公开契约，而 M1 里的 day16 断言是<b>键集合双向相等</b>
 *       （少一个 FAIL、多一个也 FAIL，它验的是白名单）—— 会当场把回归打红。</li>
 *   <li>更重要的是语义：{@code status} 是<b>管理侧状态</b>，C 端看到它没有意义
 *       （公开列表恒为 1，看见只有一种结果的字段只会引起疑问）。</li>
 * </ul>
 * <p>★ 与 {@code AdminRefundVO} / {@code RoleDetailVO} 同一条做法：<b>多出管理侧字段就另起一个类</b>，
 * 而不是把两个视角塞进同一个壳（对比 {@code UserVO} 共用：那是字段集完全相同才共用）。
 *
 * <p>⚠️ 字段与 {@code ReviewVO} 重复是刻意的「有意识的同源拷贝」——
 * 两边的 SQL 各自显式列列名，任何一边加了字段不会自动出现在另一边。
 */
@Data
@NoArgsConstructor
public class AdminReviewVO {

    private Long id;

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

    private String content;

    /** Day 83：晒图 URL（管理端审核也要能看到） */
    private java.util.List<String> images;

    /** 评价人昵称（SQL 兜底「用户****」；★ 与 C 端一样不暴露 userId） */
    private String userNickname;

    /**
     * 1 = 正常可见；0 = 已隐藏（管理员置为 0）。
     * ★ C 端的列表与两个聚合都带 {@code status = 1} ⇒ 置 0 之后立即从商品页消失、
     *   也不再计入平均分与评价数。
     */
    private Integer status;

    private LocalDateTime createdAt;
}
