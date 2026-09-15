package com.mallx.common.security;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.WebAuthenticationDetailsSource;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.List;

/**
 * 每个请求都过这里：带 token 就验、验过就"登记身份"。
 * OncePerRequestFilter = 保证一次请求只执行一次。
 */
@Component
public class JwtAuthenticationFilter extends OncePerRequestFilter {

    private static final String HEADER = "Authorization";
    private static final String PREFIX = "Bearer ";

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

                // ② 把身份登记到 SecurityContext
                //    三参数构造器：principal, credentials, authorities
                //    第二位传 null 表示不保留凭证（密码），第三位权限列表 Day 07 再接 RBAC
                //    ⚠️ 声明成 UsernamePasswordAuthenticationToken 而不是 Authentication 接口，
                //       因为 setDetails() 在实现类上，接口 Authentication 里没有这个方法
                UsernamePasswordAuthenticationToken authentication =
                        new UsernamePasswordAuthenticationToken(userId, null, List.of());
                // 附加客户端 IP、SessionId 等元信息（Day 07 做登录日志/风控时用得到）
                authentication.setDetails(new WebAuthenticationDetailsSource().buildDetails(request));

                // 强制开一个干净的 context，避免拿到线程池复用时的残留身份
                SecurityContext context = SecurityContextHolder.createEmptyContext();
                context.setAuthentication(authentication);
                SecurityContextHolder.setContext(context);

                logger.debug("已登记身份：userId=" + userId + ", username=" + username);

            } catch (JwtException | IllegalArgumentException e) {
                // 关键：这里【不能抛异常】！解析失败就当"没登录"，继续放行，
                // 由后面的 EntryPoint 统一返回 401。抛出去会变成 500。
                logger.debug("JWT 解析失败：" + e.getMessage());
            }
        }

        chain.doFilter(request, response);
    }
}
