package com.mallx.user.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 手机号注册（Day 52）。
 *
 * <p>★ 这个 DTO 里<b>没有密码字段</b>，是有意的：本功能是「手机号验证码登录」，
 * 注册时不该逼用户再想一个密码。后端会给 {@code users.password} 写一个
 * 不可登录的占位值（见 {@code UserServiceImpl#registerByPhone} 的注释），
 * 「能登录」这件事由手机号验证码独立完成。
 *
 * <p>★ 昵称可选：注册路径越短，转化越高；昵称可以后续在「我的」里补。
 * 不填时后端用「用户+手机号后四位」兜底，至少列表页不会出现一片空白。
 */
@Data
public class SmsRegisterDTO {

    @NotBlank(message = "手机号不能为空")
    @Pattern(regexp = "^1[3-9]\\d{9}$", message = "手机号格式不正确")
    private String phone;

    @NotBlank(message = "验证码不能为空")
    @Pattern(regexp = "^\\d{6}$", message = "验证码为 6 位数字")
    private String code;

    @Size(max = 50, message = "昵称最长 50 字")
    private String nickname;
}
