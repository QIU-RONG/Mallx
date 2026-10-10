package com.mallx.order.vo;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;

/**
 * ★★ 售后域申请退款时需要的「这张订单的事实」（Day 46）。
 *
 * <p>★ 为什么售后域不能自己裸读 {@code orders}：
 * 「这张单能不能退」「退多少钱」这两个问题的权威答案在<b>订单域</b> ——
 * 状态机的所有权柄都在这里（{@code OrderStatus} + 那几条 CAS UPDATE）。
 * 让别的模块自己去读状态列，等于把状态机的知识复制到第二个模块，
 * 以后状态机一改就得满仓库找（与 {@code OrderItemBuyContext} 同一条推理）。
 *
 * <p>★★ 归属条件写死在 SQL 的 {@code WHERE}（{@code user_id = #{userId}}），
 * 返回值 {@code null} <b>同时</b>表示「订单不存在」与「订单不是你的」 ——
 * 与订单详情 / 评价各处同一个 404 伪装口径：
 * <b>两种原因在数据库层就合成了一个空结果，不可区分 = 不可枚举。</b>
 *
 * <p>★ 四个字段每一个都有明确用途，多一个都没有：
 * <pre>
 *   id         定位：退款单要挂在这张订单上
 *   userId     回显与断言（★ 也是「归属已被 SQL 验过」的证据）
 *   status     判据：能不能申请、能申请哪一种售后
 *   payAmount  ★ 退款额【快照】的取值来源（V1.0 全额退款 ⇒ 退款额 = 它）
 * </pre>
 *
 * <p>⚠️ {@code @NoArgsConstructor} 必须显式写（它做 {@code resultType}）；
 * ⚠️ 别名一律下划线。
 */
@Data
@NoArgsConstructor
public class OrderRefundContext {

    /** 订单 id */
    private Long id;

    /** 买家 id */
    private Long userId;

    /** 订单状态，取值见 {@link com.mallx.order.common.OrderStatus} */
    private String status;

    /** 实付金额 —— ★ 退款额取自它，不接受客户端传值 */
    private BigDecimal payAmount;
}
