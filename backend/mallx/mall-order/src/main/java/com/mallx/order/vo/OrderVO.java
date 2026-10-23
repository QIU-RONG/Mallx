package com.mallx.order.vo;

import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 订单列表行（GET /api/orders 的 records 元素）。
 *
 * <p>刻意【不含 userId】—— 同 AddressVO 的规矩：内部归属字段不外泄。
 *
 * <p>★★ Day 65：列表行补【首件商品摘要】。原因来自用户反馈：
 * 「应该直接看到的是商品，而不是订单编号」—— 订单号是给客服对账的，
 * 顾客认的是「我买的那台手机」。摘要是<b>首件商品</b>的名字/规格/图 + 总件数，
 * 由 {@code OrderServiceImpl#listMyOrders} 用<b>一次 IN 查询</b>批量补，不做 N+1。
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

    /** 首件商品名（Day 65）；订单无明细时为 null */
    private String firstItemName;

    /** 首件商品规格名（Day 65） */
    private String firstItemSkuName;

    /** 首件商品图（Day 65） */
    private String firstItemImage;

    /** 该订单的明细行数（>1 时界面显示「等 N 件」） */
    private Integer itemCount;
}
