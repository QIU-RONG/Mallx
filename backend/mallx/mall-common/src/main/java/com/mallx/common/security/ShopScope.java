package com.mallx.common.security;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

/**
 * 店铺数据范围（Day 75）。
 *
 * <p>商户登录时，token 的 {@code perms} 里会多一条 {@code SHOP_SCOPE_<shopId>}；
 * 过滤器把它还原成权限后，业务层就能从这里读到「当前请求被限定在哪家店」。
 *
 * <p>★★ 为什么把范围做成 <b>authority</b> 而不是另存一份上下文：
 * 现有的 JWT 过滤器只认 perms，不动它就能让商户 token 一路走通鉴权；
 * 而且范围天然随请求走、不依赖 ThreadLocal 清理。
 *
 * <p>★ 平台账号（超管/商品管理员）没有这条 authority ⇒ 返回 null ⇒ 不附加任何过滤。
 */
public final class ShopScope {

    public static final String PREFIX = "SHOP_SCOPE_";

    private ShopScope() {
    }

    /** 当前请求的店铺范围；平台账号返回 null */
    public static Long currentShopId() {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth == null) {
            return null;
        }
        for (GrantedAuthority ga : auth.getAuthorities()) {
            String a = ga.getAuthority();
            if (a != null && a.startsWith(PREFIX)) {
                try {
                    return Long.valueOf(a.substring(PREFIX.length()));
                } catch (NumberFormatException ignored) {
                    return null;
                }
            }
        }
        return null;
    }

    /** 商户 token 里写进去的那条权限 */
    public static String authority(Long shopId) {
        return PREFIX + shopId;
    }
}
