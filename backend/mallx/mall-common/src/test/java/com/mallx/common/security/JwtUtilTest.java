package com.mallx.common.security;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.Arrays;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * JwtUtil 单元测试（Day 44 · 补单元测试第 1 个）。
 *
 * <p>为什么第一个测它：这是项目里**唯一一处「签发的 claim 曾经没人读」**的地方 ——
 * Day 44 的身份域漏洞（管理端 token 顶替 C 端顾客）根因就是 {@code type} 签了不用。
 * 端到端脚本（day44-identity-domain-verify.py）能证明「HTTP 层挡住了」，
 * 但**证明不了「签发侧写对了」** —— 那是毫秒级、零依赖、恰恰该由单测守的地方。
 *
 * <p>★ 本类不启动 Spring、不连数据库、不 mock：{@link JwtUtil} 只依赖
 * {@link JwtProperties}（一个 {@code @Data}），直接 {@code new} 即可 ⇒ 毫秒级。
 *
 * <p>★ 每条断言都要能失败：断言的是「token 里到底写了什么」，
 * 不是「parse 不抛异常」这种恒真句（后者在密钥配错时照样能过）。
 */
class JwtUtilTest {

    /** HS256 要求密钥 >= 32 字节 */
    private static final String SECRET = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKL";
    private static final String OTHER_SECRET = "ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ";

    private JwtUtil jwtUtil;

    @BeforeEach
    void setUp() {
        jwtUtil = newUtil(SECRET, 120);
    }

    private static JwtUtil newUtil(String secret, long expireMinutes) {
        JwtProperties props = new JwtProperties();
        props.setSecret(secret);
        props.setExpireMinutes(expireMinutes);
        return new JwtUtil(props);
    }

    // ---------------------------------------------------------------- 签发 → 解析

    @Test
    @DisplayName("C 端 token：sub / username 能原样取回")
    void generate_then_parse_returnsSubjectAndUsername() {
        String token = jwtUtil.generate(42L, "demo");

        Claims claims = jwtUtil.parse(token);

        // ★ 用字符串比：sub 在 JWT 里就是字符串，parse 出来也是 String
        assertThat(claims.getSubject()).isEqualTo("42");
        assertThat(claims.get("username", String.class)).isEqualTo("demo");
    }

    @Test
    @DisplayName("★ 身份域：C 端 token 的 type 必须是 USER")
    void generate_writesUserDomain() {
        Claims claims = jwtUtil.parse(jwtUtil.generate(1L, "demo"));

        assertThat(claims.get("type", String.class)).isEqualTo("USER");
    }

    @Test
    @DisplayName("★ 身份域：管理端 token 的 type 必须是 ADMIN，且 perms 原样带回")
    void generateForAdmin_writesAdminDomainAndPerms() {
        List<String> perms = Arrays.asList("order:ship", "product:write");

        Claims claims = jwtUtil.parse(jwtUtil.generateForAdmin(1L, "admin", perms));

        assertThat(claims.get("type", String.class)).isEqualTo("ADMIN");
        assertThat(claims.get("perms", List.class)).containsExactly("order:ship", "product:write");
    }

    @Test
    @DisplayName("★★ Day 44 漏洞的单测版：两个域的 token 数值相同但 type 必须不同")
    void userAndAdminTokens_differByTypeEvenWhenSubjectIsIdentical() {
        // users 与 admins 是两张各自从 1 起的表 ⇒ sub 撞车是常态（实测两边都是 1）
        Claims user = jwtUtil.parse(jwtUtil.generate(1L, "demo"));
        Claims admin = jwtUtil.parse(jwtUtil.generateForAdmin(1L, "admin", Arrays.asList("x")));

        assertThat(user.getSubject()).isEqualTo(admin.getSubject());      // 数值确实一样
        assertThat(user.get("type", String.class))
                .isNotEqualTo(admin.get("type", String.class));           // ★ 但域必须不同
    }

    // ---------------------------------------------------------------- 时间与签名

    @Test
    @DisplayName("过期 token 解析必须抛 JwtException（而不是静默返回 claims）")
    void expiredToken_throwsJwtException() {
        JwtUtil expiredUtil = newUtil(SECRET, -5);   // 5 分钟前就过期
        String token = expiredUtil.generate(1L, "demo");

        assertThatThrownBy(() -> jwtUtil.parse(token))
                .isInstanceOf(JwtException.class);
    }

    @Test
    @DisplayName("篡改签名的 token 必须解析失败")
    void tamperedToken_throwsJwtException() {
        String token = jwtUtil.generate(1L, "demo");
        String tampered = token.substring(0, token.length() - 3) + "aaa";

        assertThatThrownBy(() -> jwtUtil.parse(tampered))
                .isInstanceOf(JwtException.class);
    }

    @Test
    @DisplayName("另一个密钥签的 token 必须验签失败（换密钥 = 旧 token 全部失效）")
    void tokenSignedByOtherSecret_isRejected() {
        String token = newUtil(OTHER_SECRET, 120).generate(1L, "demo");

        assertThatThrownBy(() -> jwtUtil.parse(token))
                .isInstanceOf(JwtException.class);
    }

    @Test
    @DisplayName("未过期 token 解析不抛异常（上面三条「必须失败」的正向对照）")
    void validToken_doesNotThrow() {
        String token = jwtUtil.generate(1L, "demo");

        assertThatCode(() -> jwtUtil.parse(token)).doesNotThrowAnyException();
    }

    @Test
    @DisplayName("C 端 token 不带 perms claim（管理端才有）")
    void userToken_hasNoPermsClaim() {
        Claims claims = jwtUtil.parse(jwtUtil.generate(1L, "demo"));

        assertThat(claims.get("perms")).isNull();
    }
}
