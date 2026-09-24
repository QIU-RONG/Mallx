package com.mallx.server.config;

import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Swagger/OpenAPI 文档信息配置
 * 访问：http://localhost:8080/swagger-ui.html
 * <p>
 * ★ Day 24：补 {@code SecurityScheme}，让 Swagger UI 出现 <b>Authorize 按钮</b>。
 * <p>
 * 【为什么需要它】V1.0 没有前端，<b>界面就是 Swagger UI</b>（见 backlog 附一②）。
 * 而在此之前，swagger-ui 页面<b>没有 Authorize 按钮</b> ⇒ 想调一个需要登录的接口，
 * 只能手工往 header 里填 {@code Authorization: Bearer <token>} —— 而 Swagger UI
 * 的「Try it out」面板根本没有让你填自定义 header 的地方，等于<b>所有受保护接口
 * 在这个唯一的界面上都调不通</b>。
 * <p>
 * ★★ 本项目的鉴权链路有两条，必须同时声明才有效（这是最容易漏的一半）：
 * <ol>
 *   <li>{@code SecurityScheme} —— 告诉 UI「有这么一个认证方式、它叫什么名字」；</li>
 *   <li>{@code addSecurityItem} —— 告诉 UI「每个操作默认可选这个认证方式」。
 *       只加 ① 的话，UI 上会画出按钮，但操作上不会带上它
 *       （按钮存在 ≠ 请求带上 token，是两件事）。</li>
 * </ol>
 * <p>
 * ⚠️ 这里声明的只是<b>文档元数据</b>，不参与任何鉴权决策 ——
 * 防线始终是 {@code SecurityConfig} 的过滤器链 + {@code @PreAuthorize}。
 * 换句话说：在 Swagger 上填了 token 不代表能调通，填错/过期一样 401。
 * 这与项目一贯的「文档不许成为第二道防线」一致（同 {@code BrandVO} 拒绝带 productCount
 * 的理由：文档里不许出现会自行演化的真相）。
 * <p>
 * ⚠️ 用 {@code bearerAuth} 这个名字（而非 {@code JWT} / {@code Authorization}）：
 * 它是 springdoc 生态里的常见约定名，且与下方的 {@code SecurityRequirement} 逐字对应
 * —— 名字对不上时 UI 不报错，只是<b>静默地不生效</b>（同「XML 方法名＝id 逐字符」那条铁律）。
 */
@Configuration
public class OpenApiConfig {

    /** ★ scheme 名字是一处【必须逐字对应】的魔法字符串，抽成常量免得两边手写走样。 */
    private static final String SCHEME_NAME = "bearerAuth";

    @Bean
    public OpenAPI mallxOpenAPI() {
        return new OpenAPI()
                .info(new Info()
                        .title("MallX 电商系统 API")
                        .description("MallX 企业级电商系统后端接口文档"
                                + "<br>★ 受保护接口请先点右上角 <b>Authorize</b>，"
                                + "粘贴 login 接口返回的 token（<b>不用</b>自己加 \"Bearer \" 前缀）")
                        .version("0.0.1"))
                // ① 声明「存在一种叫 bearerAuth 的认证方式」
                .components(new Components().addSecuritySchemes(SCHEME_NAME,
                        new SecurityScheme()
                                .name(SCHEME_NAME)
                                .type(SecurityScheme.Type.HTTP)
                                .scheme("bearer")
                                .bearerFormat("JWT")
                                .description("登录接口返回的 token；"
                                        + "Swagger 会自动加上 \"Bearer \" 前缀")))
                // ② 让每个操作默认可选带上它
                .addSecurityItem(new SecurityRequirement().addList(SCHEME_NAME));
    }
}
