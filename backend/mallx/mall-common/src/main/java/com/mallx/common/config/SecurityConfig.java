package com.mallx.common.config;

import com.mallx.common.security.JwtAuthenticationFilter;
import com.mallx.common.security.RestAccessDeniedHandler;
import com.mallx.common.security.RestAuthenticationEntryPoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class SecurityConfig {

    private final JwtAuthenticationFilter jwtAuthenticationFilter;
    private final RestAuthenticationEntryPoint restAuthenticationEntryPoint;
    private final RestAccessDeniedHandler restAccessDeniedHandler;

    public SecurityConfig(JwtAuthenticationFilter jwtAuthenticationFilter,
                          RestAuthenticationEntryPoint restAuthenticationEntryPoint,
                          RestAccessDeniedHandler restAccessDeniedHandler) {
        this.jwtAuthenticationFilter = jwtAuthenticationFilter;
        this.restAuthenticationEntryPoint = restAuthenticationEntryPoint;
        this.restAccessDeniedHandler = restAccessDeniedHandler;

    }

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            // ① 关闭 CSRF：无状态 token 认证，不靠 Cookie，不怕 CSRF
            .csrf(AbstractHttpConfigurer::disable)
            // ② 关掉默认的登录页 / Basic 弹窗（前后端分离用不上）
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            // ③ 不使用 Session：每个请求都靠 token 自证
            .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            // ④ 白名单 + 其余全部要登录（顺序重要：anyRequest 必须放最后）
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/auth/login", "/api/auth/admin/login","/api/hello","/api/redis-check","/error").permitAll()
                .requestMatchers("/v3/api-docs/**", "/swagger-ui/**", "/swagger-ui.html").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/products/**", "/api/categories/**").permitAll()
                // ★ Day 20：优惠券「可领列表」公开。注意这里是【精确路径】，不是 "/api/coupons/**" ——
                //   通配会把 /api/coupons/my（我的券）一起公开，而白名单只认「路径 + 方法」，
                //   不认「同一个 Controller 里的不同方法」⇒ 会【静默公开】别人的券。
                //   精确路径只放行 /api/coupons 本身，/api/coupons/my 照样被 anyRequest() 兜住。
                .requestMatchers(HttpMethod.GET, "/api/coupons").permitAll()
                // ★ L5（Day 20 补漏）：品牌字典是纯公开数据（C 端品牌筛选下拉框的可选值来源）。
                //   ⚠️ 同样用【精确路径】而不是 "/api/brands/**"：白名单只认「路径 + 方法」，
                //      写 /** 之后这个前缀下将来新增的任何 GET 都会被【静默公开】
                //      （与上面 /api/coupons 那条同一个坑，Day 20 实测过）。
                .requestMatchers(HttpMethod.GET, "/api/brands").permitAll()
                .anyRequest().authenticated()
            )
            // ⑤ 认证失败返回 401、授权失败返回 403，统一 JSON（一次配全，别拆成两次调用）
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(restAuthenticationEntryPoint)
                .accessDeniedHandler(restAccessDeniedHandler))
            // ⑥ 把 JWT 过滤器插在用户名密码过滤器之前
            .addFilterBefore(jwtAuthenticationFilter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }

    /** 密码编码器：交给 Security 管理，登录时会自动用它比对 */
    @Bean
    public PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }
}
