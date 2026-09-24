package com.mallx.admin.vo;

import lombok.Data;

import java.math.BigDecimal;

/**
 * 仪表盘概览（{@code GET /api/admin/dashboard/overview}）—— 4 个标量快照。
 *
 * <p>★ 与 {@code /trend} <b>刻意分成两个端点</b>：快照是「当下值」，时间序列是「一段区间」。
 * 两者的变化频率、缓存语义、入参（trend 有 {@code days}）都不同；
 * 合并成一个接口会让 {@code days} 这个参数渗透到不需要它的那半边。
 *
 * <p>★ 字段类型选 {@code Long} / {@code BigDecimal} 而不是 {@code long}：
 * 将来若某个指标改成「不可见」（比如无权限看销售额），能返回 {@code null}
 * 而不是骗人的 {@code 0}（{@code 0} 会与「真的没有」不可区分）。
 */
@Data
public class DashboardOverviewVO {

    /** 用户总数（users 全表 count —— 含已禁用，禁用不是删除） */
    private Long userCount;

    /** 商品数（★ 口径：{@code is_deleted = 0} 的全部商品，含下架；不是「上架数」） */
    private Long productCount;

    /** 订单总数（全表 count，不分状态 —— 含已取消，那也是一笔真实发生过的订单） */
    private Long orderCount;

    /**
     * 销售额（★ 口径：<b>支付流水口径</b>
     * —— {@code SELECT coalesce(sum(amount), 0) FROM payments WHERE status='SUCCESS'}）。
     *
     * <p>为什么不取 {@code orders.pay_amount}：{@code orders} 记的是「应当收的钱」，
     * {@code payments} 记的是「钱实际动过的事实」。将来加退款（{@code REFUNDED}）时，
     * 支付口径天然扣得掉（一条状态判断），订单口径则要额外维护「已退款金额」。
     * ⚠️ 这是本项目反复踩的口径漂移，所以口径<b>写进 javadoc</b>，不只写在文档里。
     */
    private BigDecimal salesAmount;
}
