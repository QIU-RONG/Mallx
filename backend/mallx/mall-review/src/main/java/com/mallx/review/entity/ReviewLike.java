package com.mallx.review.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/** 评价点赞（Day 89）：一人一条评价一次 */
@Data
@TableName("review_likes")
public class ReviewLike {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long reviewId;

    private Long userId;

    private LocalDateTime createdAt;
}
