package com.mallx.marketing.vo;

import lombok.Data;

import java.time.LocalDateTime;

/** 优惠券领取记录（管理端，Day 103） */
@Data
public class CouponRecordVO {

    private Long id;
    private Long userId;
    private String userName;
    private String status;
    private LocalDateTime receivedAt;
    private LocalDateTime usedAt;
    private Long orderId;
}
