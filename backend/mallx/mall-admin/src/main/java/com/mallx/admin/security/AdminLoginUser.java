package com.mallx.admin.security;

import lombok.Getter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;

import java.util.Collection;
import java.util.List;

/**
 * Security 眼里的"管理员"：把 admins 表的一行 + 拼好的权限集合翻译成 UserDetails。
 * <p>
 * 与 C 端 {@code com.mallx.user.security.LoginUser} 的唯一本质区别：
 * {@link #getAuthorities()} 不再返回空集合 —— 管理端鉴权能不能生效，就看这一个方法。
 */
@Getter
public class AdminLoginUser implements UserDetails {

    private final Long adminId;
    private final String username;
    private final String password;
    private final Integer status;

    /**
     * 权限集合，形如：
     * [product:list, product:create, product:update, product:delete, ROLE_SUPER_ADMIN]
     * <p>
     * 由 {@link AdminAccountService} 联查 RBAC 表拼好后传进来，本类只负责"携带"。
     */
    private final List<String> permissions;

    public AdminLoginUser(Long adminId, String username, String password,
                          Integer status, List<String> permissions) {
        this.adminId = adminId;
        this.username = username;
        this.password = password;
        this.status = status;
        this.permissions = permissions;
    }

    /**
     * ★★★ 今天最重要的一个方法 ★★★
     * 把字符串权限集合翻译成 Security 认识的 GrantedAuthority。
     * <p>
     * 这里返回什么，@PreAuthorize("hasAuthority('xxx')") 就能匹配什么；
     * 一旦返回空集合，所有写接口对所有人都是 403。
     */
    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return permissions.stream()
                .map(SimpleGrantedAuthority::new)
                .toList();
    }

    @Override
    public String getPassword() {
        return password;
    }

    @Override
    public String getUsername() {
        return username;
    }

    // ---------- 以下四个 isXxx 是 UserDetails 的"账号状态开关" ----------

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

    /** status = 1 才算启用；被禁用的管理员会在登录时被拦下 */
    @Override
    public boolean isEnabled() {
        return status != null && status == 1;
    }
}
