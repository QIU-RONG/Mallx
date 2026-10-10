package com.mallx.common.security;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.WebAuthenticationDetailsSource;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

/**
 * 每个请求都过这里：带 token 就验、验过就"登记身份"。
 * OncePerRequestFilter = 保证一次请求只执行一次。
 */
@Component
public class JwtAuthenticationFilter extends OncePerRequestFilter {

    private static final String HEADER = "Authorization";
    private static final String PREFIX = "Bearer ";

    /**
     * ★★ 身份域 authority（Day 44）。**不是权限码**，只表达「这个 token 是从哪个域签出来的」。
     *
     * <p>为什么必须有它：两种 token 的主体都是「一个 {@code Long}」——
     * 过滤器的 principal 就是 token 的 {@code sub}，C 端是 {@code users.id}、
     * 管理端是 {@code admins.id}，而这是 {@code 01-schema.sql} 里<b>两张独立的表</b>，
     * id 各自从 1 起 ⇒ <b>同一个数值可能代表两个完全不同的人</b>。
     *
     * <p>不加域标记的后果是实测到的（Day 44 取证）：超管 {@code sub=1} 打
     * {@code GET /api/users/me} 返回了顾客 {@code demo} 的手机号 / 昵称 / 邮箱，
     * 打 {@code GET /api/orders} 返回了该顾客的全部 6 张订单 —— 因为过滤器只看
     * {@code sub}，把管理端的 {@code adminId} 当成了 {@code userId}。
     *
     * <p>分清域之后 {@code SecurityConfig} 就能按路径把关：
     * {@code /api/admin/**} 只收 {@code DOMAIN_ADMIN}，其余只收 {@code DOMAIN_USER}。
     */
    public static final String DOMAIN_USER = "DOMAIN_USER";
    public static final String DOMAIN_ADMIN = "DOMAIN_ADMIN";

    private final JwtUtil jwtUtil;

    public JwtAuthenticationFilter(JwtUtil jwtUtil) {
        this.jwtUtil = jwtUtil;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {

        String header = request.getHeader(HEADER);

        if (header != null && header.startsWith(PREFIX)) {
            String token = header.substring(PREFIX.length());
            try {
                // ① 解析 token：sub 里装的是签发时放进去的 userId（字符串形式）
                Claims claims = jwtUtil.parse(token);
                Long userId = Long.valueOf(claims.getSubject());
                String username = claims.get("username", String.class);


                // ★★ 身份域（Day 44）：type=ADMIN / USER 决定这个 token 属于哪个域。
                //   ⚠️ 域不明时【fail closed】：不登记身份（等同未登录 → 401），
                //      而不是猜「大概是 C 端」—— 猜错一次就是那个越权漏洞本身。
                //      抛 IllegalArgumentException 会被下面的 catch 接住，语义与
                //      「token 解析失败就当没登录」一致（绝不抛到 500）。
                String type = claims.get("type", String.class);
                if (!"USER".equals(type) && !"ADMIN".equals(type)) {
                    throw new IllegalArgumentException("缺少/未知的身份域 type=" + type);
                }

                // perms 照旧（C 端 token 本来就没有这个 claim ⇒ 权限集只有域标记一项）
                List<GrantedAuthority> authorities = new ArrayList<>();
                authorities.add(new SimpleGrantedAuthority(
                        "ADMIN".equals(type) ? DOMAIN_ADMIN : DOMAIN_USER));
                List<?> perms = claims.get("perms",List.class);
                if(perms != null){
                    for(Object p  : perms){
                        authorities.add(new SimpleGrantedAuthority(String.valueOf(p)));
                    }
                }

                // ② 把身份登记到 SecurityContext
                //    三参数构造器：principal, credentials, authorities
                //    第二位传 null 表示不保留凭证（密码），第三位权限列表 Day 07 再接 RBAC
                //    ⚠️ 声明成 UsernamePasswordAuthenticationToken 而不是 Authentication 接口，
                //       因为 setDetails() 在实现类上，接口 Authentication 里没有这个方法
                UsernamePasswordAuthenticationToken authentication =
                        new UsernamePasswordAuthenticationToken(userId, null, authorities);
                // 附加客户端 IP、SessionId 等元信息（Day 07 做登录日志/风控时用得到）
                authentication.setDetails(new WebAuthenticationDetailsSource().buildDetails(request));

                // 强制开一个干净的 context，避免拿到线程池复用时的残留身份
                SecurityContext context = SecurityContextHolder.createEmptyContext();
                context.setAuthentication(authentication);
                SecurityContextHolder.setContext(context);

                logger.debug("已登记身份：type=" + type + ", userId=" + userId + ", username=" + username);

            } catch (JwtException | IllegalArgumentException e) {
                // 关键：这里【不能抛异常】！解析失败就当"没登录"，继续放行，
                // 由后面的 EntryPoint 统一返回 401。抛出去会变成 500。
                logger.debug("JWT 解析失败：" + e.getMessage());
            }
        }

        chain.doFilter(request, response);
    }
}
