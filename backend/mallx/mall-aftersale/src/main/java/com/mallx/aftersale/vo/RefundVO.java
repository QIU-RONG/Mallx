package com.mallx.aftersale.vo;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 退款单视图（C 端「我的售后」用）—— Day 46。
 *
 * <p>★ 与 {@link AdminRefundVO} 的分工，和 {@code OrderVO} / {@code AdminOrderVO} 完全同构：
 * <pre>
 *   RefundVO       买家看自己的那张单      —— 不含任何别人的信息
 *   AdminRefundVO  运营看全站的售后单      —— 多带 order_no / user_nickname
 * </pre>
 * ★ 不合并成一个 VO：给 C 端 VO 加两个字段，等于让 C 端响应跟着变胖，
 * 而「运营要看买家是谁」这个需求与买家本人无关（理由同 {@code AdminOrderVO}）。
 *
 * <p>★ 五个业务时间戳<b>全部</b>出参：售后单的进度条就是靠它们画的
 * （申请 → 审核 → 寄出 → 收货 → 退款），缺一个就有一段进度无法表达。
 *
 * <p>⚠️ {@code @NoArgsConstructor} 必须显式写 —— 它做 {@code resultType}，
 * 靠「反射无参构造 + setter」装填。
 * ⚠️ 别名一律<b>下划线</b>：这是唯一在 {@code map-underscore-to-camel-case}
 * 两态下都成立的写法。
 */
@Data
@NoArgsConstructor
public class RefundVO {

    private Long id;

    private String refundNo;

    private Long orderId;

    /** REFUND_ONLY / RETURN_REFUND */
    private String type;

    /** APPLIED / APPROVED / REJECTED / RETURNING / REFUNDING / SUCCESS / CANCELLED */
    private String status;

    /** ★ 退款额快照 */
    private BigDecimal amount;

    private String reason;

    /** 管理端审核备注（拒绝原因）—— 买家必须看得到，否则不知道为什么被拒 */
    private String remark;

    /** 退货物流单号（仅 RETURN_REFUND） */
    private String trackingNo;

    private LocalDateTime appliedAt;

    private LocalDateTime auditedAt;

    private LocalDateTime shippedAt;

    private LocalDateTime receivedAt;

    private LocalDateTime refundedAt;

    private LocalDateTime createdAt;
}
