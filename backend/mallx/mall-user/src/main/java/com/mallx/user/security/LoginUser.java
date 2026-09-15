package com.mallx.user.security;

import lombok.Getter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;

import java.util.Collection;
import java.util.List;

/**
 * Security 眼里的"用户"：把 users 表的一行翻译成 UserDetails。
 */
@Getter
public class LoginUser implements UserDetails {

    private Long userId;
    private String username;
    private String password;
    private Integer status;

    public LoginUser(Long userId, String username, String password, Integer status) {
        this.userId = userId;
        this.username = username;
        this.password = password;
        this.status = status;
    }

    /** 权限列表：今天先留空，Day 07 接 RBAC 时再填 */
    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return List.of();
    }

    @Override
    public boolean isAccountNonExpired() {
        return true;
    }

    @Override
    public boolean isAccountNonLocked() {
        return true;
    }

    @Override
    public boolean isCredentialsNonExpired() {
        return true;
    }

    /** status = 1 才算启用；被禁用的用户会在登录时被拦下 */
    @Override
    public boolean isEnabled() {
        return status != null && status == 1;
    }
}
