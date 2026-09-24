package com.mallx.order.vo;

import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

/**
 * 订单详情（GET /api/orders/{id}）—— 订单头 + 明细列表。
 *
 * <p>刻意【不含 userId】（同 AddressVO 的规矩）。
 * 四个业务时间戳原样带出：未流转的节点就是 {@code null}，不做「假默认值」。
 */
@Data
public class OrderDetailVO {

    private Long id;

    private String orderNo;

    private BigDecimal totalAmount;

    private BigDecimal payAmount;

    /**
     * 优惠额快照（L7，Day 22 补）。
     *
     * <p>Day 21 就把它落库了（{@code orders.discount_amount NOT NULL DEFAULT 0}），
     * 但两个出参 VO 一直没带出来 ⇒ 详情页只看得到「实付 80」，看不到「省了 20」。
     * 前端只能靠 {@code total − pay} 自己反推 —— 而 Day 21 特意落库快照，
     * 正是为了<b>不让下游反推</b>（规则一变口径就漂）。
     *
     * <p>★ 恒等式：{@code payAmount = totalAmount − discountAmount}。
     * 断言时要<b>三个数一起断</b>，光断 discount 排除不了 pay 算错。
     * <p>★ 不用券时是 {@code 0.00} 而不是 {@code null}（与 DB 的 NOT NULL DEFAULT 0 对齐）。
     */
    private BigDecimal discountAmount;

    private String status;

    // ---------------- 收货快照 ----------------

    private String receiverName;

    private String receiverPhone;

    private String receiverAddress;

    // ---------------- 时间戳 ----------------

    private LocalDateTime createdAt;

    /** 以下四个未流转时为 null */
    private LocalDateTime paidAt;

    private LocalDateTime shippedAt;

    private LocalDateTime completedAt;

    private LocalDateTime cancelledAt;

    /** 订单明细（快照值） */
    private List<OrderItemVO> items;
}
