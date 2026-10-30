package com.mallx.review.vo;

import lombok.Data;

/** 点赞结果（Day 89）：前端据此更新按钮态与计数 */
@Data
public class ReviewLikeVO {

    private boolean liked;

    private long likeCount;
}
