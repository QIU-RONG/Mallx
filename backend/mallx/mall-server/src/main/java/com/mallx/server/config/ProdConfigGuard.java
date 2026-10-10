package com.mallx.server.config;

import org.springframework.context.annotation.Profile;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 生产 profile 的「必填配置」闸门（V1.4 · D42）。
 *
 * <h3>为什么需要它 —— 一个实测出来的坑</h3>
 * 原本以为把 {@code application-prod.yml} 里的值写成 {@code ${DB_PASSWORD}}（**不带** {@code :默认值}）
 * 就够了：缺失时 Spring 会抛 {@code Could not resolve placeholder} 让应用起不来。
 * 实测**不是这样**：
 *
 * <pre>
 * docker run -e SPRING_PROFILES_ACTIVE=prod -e DB_HOST=nope ... （**故意不给 DB_PASSWORD**）
 *   ⇒ state=running  exit=0  Started MallXApplication in 8.5 seconds
 * </pre>
 *
 * 原因是 Spring 的占位符是**懒解析**的 —— 只有真正有人去读
 * {@code spring.datasource.password} 时才解析。而 Hikari 连接池是懒初始化、
 * MyBatis-Plus 启动期不碰数据库，于是「没人读 ⇒ 没人报错 ⇒ 应用带着一个空密码起来了」，
 * 直到第一次查库才炸。**这恰好是最危险的那种失败：服务看起来是好的。**
 * （对照：{@code mallx.jwt.secret} 由 {@code JwtUtil} 在构造时读取，所以它是真的会快速失败的。）
 *
 * <h3>做法</h3>
 * 在启动时**主动读一遍**这些必填项。任何一项解析失败或为空 ⇒ 构造器抛异常 ⇒
 * Spring 上下文启动失败 ⇒ 进程非零退出。判据从「人去看日志里有没有那句话」变成**退出码**。
 *
 * <p>刻意只挂在 {@code prod} profile 下：本地/CI 走默认 profile，
 * {@code application.yml} 里那些开发默认值仍然生效，「clone 下来就能跑」不被破坏。
 */
@Component
@Profile("prod")
public class ProdConfigGuard {

    /**
     * 必填项。选择标准见 {@code application-prod.yml} 开头：
     * **错了会「静默地用错值」的才必填**；错了会明确报错或只是降级的（Redis / RabbitMQ）
     * 不算 —— 它们有降级路径，要求必填只会把「可降级」升级成「起不来」。
     */
    private static final Map<String, String> REQUIRED;

    static {
        Map<String, String> m = new LinkedHashMap<>();
        m.put("spring.datasource.url", "DB_HOST / DB_PORT / DB_NAME");
        m.put("spring.datasource.username", "DB_USERNAME");
        m.put("spring.datasource.password", "DB_PASSWORD");
        m.put("mallx.jwt.secret", "JWT_SECRET");
        REQUIRED = java.util.Collections.unmodifiableMap(m);
    }

    public ProdConfigGuard(Environment env) {
        List<String> missing = new ArrayList<>();
        for (Map.Entry<String, String> e : REQUIRED.entrySet()) {
            String value;
            try {
                value = env.getProperty(e.getKey());
            } catch (IllegalArgumentException unresolved) {
                // `${DB_PASSWORD}` 没有兜底、环境里也没有该变量 ⇒ 占位符解析失败。
                // 这正是要拦的情况：收进 missing，而不是让它以原始异常裸奔。
                value = null;
            }
            if (value == null || value.isBlank()) {
                missing.add(e.getKey() + "（环境变量 " + e.getValue() + "）");
            }
        }
        if (!missing.isEmpty()) {
            throw new IllegalStateException(
                    "生产 profile(prod) 启动中止 —— 以下必填配置缺失或为空：" + missing
                            + "。它们在 application-prod.yml 里【刻意不给默认值】："
                            + "用开发默认值静默跑起来（连错库、或用仓库里公开的密钥签发管理员 token）"
                            + "比启动失败危险得多。请检查 deploy/.env 与编排里的 environment。");
        }
    }
}
