package com.mallx.server.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Swagger/OpenAPI 文档信息配置
 * 访问：http://localhost:8080/swagger-ui.html
 */
@Configuration
public class OpenApiConfig {

    @Bean
    public OpenAPI mallxOpenAPI() {
        return new OpenAPI().info(new Info()
                .title("MallX 电商系统 API")
                .description("MallX 企业级电商系统后端接口文档")
                .version("0.0.1"));
    }
}
