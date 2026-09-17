package com.mallx.common.security;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtBuilder;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.springframework.stereotype.Component;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.util.Date;
import java.util.List;

/**
 * JWT 工具：签发 + 解析。
 * jjwt 0.12 起 API 大改（parserBuilder/parseClaimsJws 已弃用），这里用新写法。
 */
@Component
public class JwtUtil {

    private final JwtProperties props;

    /** 密钥对象：构造一次复用，比每次现算便宜 */
    private final SecretKey key;

    public JwtUtil(JwtProperties props) {
        this.props = props;
        this.key = Keys.hmacShaKeyFor(props.getSecret().getBytes(StandardCharsets.UTF_8));
    }

    /** 签发 token */
    public String generate(Long userId, String username) {
        Date now = new Date();
        Date expiration = new Date(now.getTime() + props.getExpireMinutes() * 60_000L);

        JwtBuilder builder = Jwts.builder()
                .subject(String.valueOf(userId))
                .claim("username", username)
                .claim("type", "USER")
                .issuedAt(now)
                .notBefore(now)
                .expiration(expiration)
                .signWith(key);
        return builder.compact();
    }

    /** 解析并验签；token 非法/过期会抛 JwtException 子类 */
    public Claims parse(String token) {
        return Jwts.parser()
                .verifyWith(key)
                .build()
                .parseSignedClaims(token)
                .getPayload();
    }

    public String generateForAdmin(Long adminId, String username, List<String> permissions) {
        Date now = new Date();
        Date expiration = new Date(now.getTime() + props.getExpireMinutes() * 60_000L);

        JwtBuilder builder =  Jwts.builder().subject(String.valueOf(adminId))
                .claim("username",username)
                .claim("type","ADMIN")
                .claim("perms",permissions)
                .issuedAt(now)
                .notBefore(now)
                .expiration(expiration)
                .signWith(key);

        return builder.compact();
    }


}
