package com.mallx.user.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import lombok.Data;

/**
 * 发送短信验证码（Day 52）。
 *
 * <p>★ 手机号除了 {@code @NotBlank} 还要做 {@code @Pattern} 格式校验，不是多余的：
 * 验证码在 Redis 里以<b>手机号作为 key</b>，格式不控住的话
 * 「13800000001」和「13800000001 」（多一个空格）会存成两个 key ——
 * 而用户看起来是同一个号，只会觉得「验证码明明收到了却说错误」。
 */
@Data
public class SmsSendDTO {

    @NotBlank(message = "手机号不能为空")
    @Pattern(regexp = "^1[3-9]\\d{9}$", message = "手机号格式不正确")
    private String phone;
}
