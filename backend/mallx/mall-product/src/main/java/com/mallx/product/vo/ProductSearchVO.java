package com.mallx.product.vo;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;

/**
 * C 端搜索结果项（Day 19）。
 *
 * <p>与 {@link ProductVO} 的区别只有一个：多一个 {@link #searchRank}（相关性得分）。
 * 单独立一个 VO 而不是给 ProductVO 加字段 —— C 端列表/管理端列表都不需要 rank，
 * 加在公共 VO 上会让它们平白多出一个恒为 null 的字段。
 *
 * <p>★ 字段与 XML 里的列别名映射规则：PG 会把未加引号的别名折成小写，
 * 所以别名一律写成下划线形式（{@code main_image AS main_image}），
 * 再由 MyBatis-Plus 的驼峰映射转成 {@code mainImage}。
 * 写成 {@code AS mainImage} 会被折成 {@code mainimage} ⇒ 字段静默为 null，且不报错。
 */
@Data
@NoArgsConstructor
public class ProductSearchVO {

    private Long id;

    private String name;

    private String subtitle;

    /** ★ XML 里别名必须写 main_image（下划线） */
    private String mainImage;

    private Long categoryId;

    private String categoryName;

    /** 该商品「在售 + 未删」SKU 的最低价；一个都没有时为 null */
    private BigDecimal minPrice;

    /**
     * 全文相关性得分：{@code ts_rank(search_vector, plainto_tsquery('simple', keyword))}。
     *
     * <p>★ XML 里的别名必须是 {@code search_rank} —— 不是 {@code rank}：
     * {@code rank} 是 PostgreSQL 的<b>保留字</b>（窗口函数名），不加引号当列别名会报语法错。
     *
     * <p>★ 无关键词时为 <b>0</b>（不是 null）：{@code ts_rank(v, ''::tsquery)} 返回 0，
     * 所以 {@code ORDER BY search_rank DESC, p.id ASC} 这一条排序在两种情况下都成立
     * （全 0 时退化成按 id 排，顺序稳定）。
     *
     * <p>★ 类型是 {@code Float}：PG 的 {@code ts_rank} 返回 {@code real}（float4）。
     */
    private Float searchRank;
}
