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
