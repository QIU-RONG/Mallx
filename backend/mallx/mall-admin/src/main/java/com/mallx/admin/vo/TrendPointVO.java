package com.mallx.admin.vo;

import lombok.Data;

import java.math.BigDecimal;

/**
 * 趋势图上的一个点（{@code GET /api/admin/dashboard/trend}）—— 一天两个值。
 *
 * <p>★ 一个点带两个指标（订单量 + 销售额），而不是两条独立的序列：
 * 「某天的订单数」与「某天的销售额」天然同一天对齐，拆成两个 List 只会
 * 让前端自己对日期（而且一旦某天缺数据，两个 List 的长度就对不上）。
 *
 * <p>★★ <b>「按天补 0」是本端点最容易错的地方</b>：
 * 直觉写法 {@code GROUP BY date(created_at)} 只会返回<b>有数据的那些天</b> ——
 * 7 天里只有 2 天有单，就只回 2 个点。前端画折线时那 5 天会<b>消失</b>，
 * 曲线看起来照样平滑（相邻点直接连线），一眼看不出少了数据。
 * ⇒ 必须拿日期骨架 LEFT JOIN 聚合结果，缺的日子显式补 0。
 */
@Data
public class TrendPointVO {

    /** 日期，固定 {@code yyyy-MM-dd}（字符串 —— 前端分组/显示都直接用，不需要再转） */
    private String date;

    /** 当天订单量（无订单的日子补 0，不是 null） */
    private Long orderCount;

    /** 当天销售额（支付流水口径；无收款的日子补 0，不是 null） */
    private BigDecimal salesAmount;
}
