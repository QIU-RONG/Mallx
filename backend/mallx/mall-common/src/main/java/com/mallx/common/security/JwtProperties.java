package com.mallx.common.security;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * JWT 配置项，对应 application.yml 里的 mallx.jwt.*
 */
@Data
@Component
@ConfigurationProperties(prefix = "mallx.jwt")
public class JwtProperties {

    /** 签名密钥（HS256 要求 >= 32 字节） */
    private String secret;

    /** token 有效期（分钟） */
    private long expireMinutes = 120;
}
