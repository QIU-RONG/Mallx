package com.mallx.server.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import java.nio.file.Paths;

/**
 * 上传目录的静态映射（Day 74）。
 *
 * <p>把 {@code /uploads/**} 映射到配置的本地目录（默认 {@code ./uploads}）。
 * 生产环境如果前面挂了 Caddy/Nginx，更推荐由反向代理直接服务这个目录（性能更好），
 * 这个映射保证「本地开发 + 无代理部署」也能访问。
 */
@Configuration
public class UploadWebConfig implements WebMvcConfigurer {

    private final String uploadDir;

    public UploadWebConfig(@Value("${mallx.upload.dir:./uploads}") String uploadDir) {
        this.uploadDir = uploadDir;
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        String location = Paths.get(uploadDir).toAbsolutePath().normalize().toUri().toString();
        // ★ location 必须以 / 结尾，否则最后一段会被当成文件名
        if (!location.endsWith("/")) {
            location = location + "/";
        }
        registry.addResourceHandler("/uploads/**").addResourceLocations(location);
    }
}
