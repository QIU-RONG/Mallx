package com.mallx;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * MallX 启动类
 * <p>
 * 位于 com.mallx 根包下，默认组件扫描覆盖所有业务模块
 * （com.mallx.user / com.mallx.product / ...）
 */

@EnableScheduling
@MapperScan("com.mallx.**.mapper")
@SpringBootApplication
public class MallXApplication {

    public static void main(String[] args) {
        SpringApplication.run(MallXApplication.class, args);
    }
}
