package com.mallx.review.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

/**
 * 管理端改评价状态（{@code PUT /api/admin/reviews/{id}/status}，Day 55）。
 *
 * <p>★ 与 {@code UserStatusUpdateDTO} 同构：<b>定点端点</b>，只留 status 一个字段。
 * 不做「编辑评价内容」—— 平台改用户写的话，那句话就不再是用户的评价了。
 * 「隐藏」是可追溯的处理方式（数据还在，只是不展示），这也是本项目一贯的
 * 「软删优先于改写」。
 *
 * <p>⚠️ 用 {@code Integer} 而非 {@code int}：{@code int} 的默认值 0 会把「不传」
 * 静默判成「隐藏」—— 那是最坏的一种静默。{@code @NotNull} 把「不传」挡成 400。
 */
@Data
public class ReviewStatusUpdateDTO {

    /** 1 = 显示，0 = 隐藏 */
    @NotNull(message = "status 不能为空（1=显示 0=隐藏）")
    @Min(value = 0, message = "status 只能是 0（隐藏）或 1（显示）")
    @Max(value = 1, message = "status 只能是 0（隐藏）或 1（显示）")
    private Integer status;
}
