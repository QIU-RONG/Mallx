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
                // ★ Day 52：手机号验证码登录 / 注册的三条路径。
                //   ⚠️ 依然【逐条精确路径】，绝不写 "/api/auth/sms/**" ——
                //      白名单只认「路径 + 方法」，写成通配之后，这个前缀下将来新增的任何接口
                //      都会被【静默公开】。本项目在 /api/coupons、/api/brands、/actuator
                //      上已经踩过三次同一个坑，不再踩第四次。
                .requestMatchers(HttpMethod.POST,
                                 "/api/auth/sms/send",
                                 "/api/auth/sms/login",
                                 "/api/auth/sms/register").permitAll()
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
                // ★ V1.4 · D42：actuator 探针白名单。**依然是精确路径**，理由同上一条 ——
                //   ⚠️ 绝不能写 "/actuator/**"：那会把 metrics / env / configprops / heapdump
                //      这类「暴露数据源地址、环境变量、堆转储」的端点一起【静默公开】。
                //   只放行容器编排放健康检查要打的那几条（路径必须与 Dockerfile 的
                //   HEALTHCHECK 逐字符一致，否则探针拿到 401 → 容器永远 unhealthy）。
                //   ★ /actuator/info 只含 application.yml 里显式写入的 app.name/description
                //     （management.info.env 默认关闭），不含任何环境细节。
                .requestMatchers("/actuator/health",
                                 "/actuator/health/liveness",
                                 "/actuator/health/readiness",
                                 "/actuator/info").permitAll()
                // ★★★ Day 44 · 身份域隔离。**下面三条必须放在 anyRequest 之前。**
                //   背景：principal 只是 token 的 sub（一个 Long），而 `users` 与 `admins`
                //   是 01-schema.sql 里两张【独立的表】、id 各自从 1 起 ⇒ 光看 sub 分不出
                //   「顾客 1」和「超管 1」。Day 44 实测：超管 token（sub=1）打
                //   `GET /api/users/me` 返回了顾客 demo 的手机号/昵称/邮箱，打
                //   `GET /api/orders` 返回了该顾客全部 6 张订单。
                //   ⇒ 过滤器已按 type claim 写入 DOMAIN_USER / DOMAIN_ADMIN，这里按路径把关：
                //     跨域使用一律走 AccessDeniedHandler ⇒ **真 HTTP 403**（不是 200+code）。
                .requestMatchers("/api/admin/**").hasAuthority(JwtAuthenticationFilter.DOMAIN_ADMIN)
                // ⚠️ 唯一的例外：发货是【管理端动作】，却与 C 端接口同处 OrderController、
                //   共用 /api/orders 前缀（该类注释里写过「同一个类里出现两种鉴权模型是有意为之」）。
                //   漏掉这一行 ⇒ 发货立刻 403（M1 的 day15-ship-confirm 会红）。
                //   ★ 将来若新增「管理端动作挂在 C 端路径下」的接口，**必须同时在这里加一行**。
                .requestMatchers(HttpMethod.POST, "/api/orders/*/ship")
                    .hasAuthority(JwtAuthenticationFilter.DOMAIN_ADMIN)
                .anyRequest().hasAuthority(JwtAuthenticationFilter.DOMAIN_USER)
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
