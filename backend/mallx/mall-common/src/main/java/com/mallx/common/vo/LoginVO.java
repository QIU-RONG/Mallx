package com.mallx.common.vo;

import lombok.AllArgsConstructor;
import lombok.Data;

/**
 * 登录响应体（C 端 / 管理端共用）。
 * <p>
 * 放在 mall-common 是为了让 mall-admin 也能用 —— mall-admin 只依赖 mall-common。
 */
@Data
@AllArgsConstructor
public class LoginVO {

    private String token;

    private String tokenType;

    /** 有效期（秒） */
    private long expiresIn;

    /** 登录主体 id：C 端是 userId，管理端是 adminId */
    private Long userId;

    private String username;

    private String nickname;
}
