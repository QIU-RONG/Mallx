package com.mallx.common.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

/**
 * 登录请求体（C 端 / 管理端共用）。
 * <p>
 * 放在 mall-common 是为了让 mall-admin 也能用 —— mall-admin 只依赖 mall-common，
 * 引用不了 mall-user 里的类。
 */
@Data
public class LoginDTO {

    @NotBlank(message = "用户名不能为空")
    private String username;

    @NotBlank(message = "密码不能为空")
    private String password;
}
