package com.mallx.server.controller;

import com.mallx.common.api.Result;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import javax.sql.DataSource;

/**
 * Day 02 验收接口
 */
@RestController
@RequestMapping("/api")
public class HelloController {

    @Autowired
    private DataSource dataSource;

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
}
