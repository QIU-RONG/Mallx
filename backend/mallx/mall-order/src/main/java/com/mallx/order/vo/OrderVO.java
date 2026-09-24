package com.mallx.order.vo;

import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 订单列表行（GET /api/orders 的 records 元素）。
 *
 * <p>刻意【不含 userId】—— 同 AddressVO 的规矩：内部归属字段不外泄。
 * 收货信息带上是因为列表里用户要看「寄给谁」；明细不带（列表页不展开，避免 N+1）。
 */
@Data
public class OrderVO {

    private Long id;

    private String orderNo;

    private BigDecimal totalAmount;

    private BigDecimal payAmount;

    /**
     * 优惠额快照（L7，Day 22 补）。理由与恒等式见 {@code OrderDetailVO#discountAmount}。
     * <p>★ 列表页也需要它：用户看到「实付 80」时最常问的就是「我那张券用在哪了」。
     */
    private BigDecimal discountAmount;

    private String status;

    private String receiverName;

    private String receiverPhone;

    private String receiverAddress;

    private LocalDateTime createdAt;
}
