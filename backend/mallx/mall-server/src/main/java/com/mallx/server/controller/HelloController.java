package com.mallx.server.controller;

import com.mallx.common.api.Result;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import javax.sql.DataSource;
import java.time.Duration;

/**
 * Day 02 验收接口（D37 起兼任 Redis 冒烟）
 */
@RestController
@RequestMapping("/api")
public class HelloController {

    @Autowired
    private DataSource dataSource;

    @Autowired
    private StringRedisTemplate stringRedisTemplate;

    /** 基础连通性：GET /api/hello */
    @GetMapping("/hello")
    public Result<String> hello() {
        return Result.ok("Hello MallX");
    }

    /** 数据库连通性验证：GET /api/db-check —— 实际查询 PostgreSQL（Docker 容器） */
    @GetMapping("/db-check")
    public Result<String> dbCheck() {
        try {
            JdbcTemplate jdbc = new JdbcTemplate(dataSource);
            String version = jdbc.queryForObject(
                    "select version()", String.class);
            return Result.ok("DB 连接成功: " + version);
        } catch (Exception e) {
            return Result.error("DB 连接失败: " + e.getMessage());
        }
    }

    /**
     * Redis 连通性验证：GET /api/redis-check（V1.1 · D37）。
     * <p>真实写入 + 读回（10 秒过期），不是只 PING —— 顺手验证序列化链路与过期语义。
     * <p>★ 与 db-check 同款哲学：失败返回 200 + body.code，不靠 HTTP 500 表达。
     */
    @GetMapping("/redis-check")
    public Result<String> redisCheck() {
        try {
            stringRedisTemplate.opsForValue().set("mallx:smoke:ping", "pong", Duration.ofSeconds(10));
            String back = stringRedisTemplate.opsForValue().get("mallx:smoke:ping");
            if (!"pong".equals(back)) {
                return Result.error("Redis 读写不一致: back=" + back);
            }
            return Result.ok("Redis 连接成功: set/get=pong (ttl=10s)");
        } catch (Exception e) {
            return Result.error("Redis 连接失败: " + e.getMessage());
        }
    }
}
