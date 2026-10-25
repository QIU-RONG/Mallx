package com.mallx.review.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/** 评价图片（Day 80）：一张图一行，按 sort 排列 */
@Data
@TableName("review_images")
public class ReviewImage {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long reviewId;

    private String imageUrl;

    private Integer sort;

    private LocalDateTime createdAt;
}
