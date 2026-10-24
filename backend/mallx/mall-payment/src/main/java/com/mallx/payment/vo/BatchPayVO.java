package com.mallx.payment.vo;

import lombok.Data;

import java.math.BigDecimal;
import java.util.List;

/** 批量支付结果（Day 78） */
@Data
public class BatchPayVO {

    private List<Long> orderIds;

    /** 本次共支付多少（各单实付之和，服务端计算） */
    private BigDecimal totalAmount;

    private int count;
}
