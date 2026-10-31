package com.mallx.ai.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * AI 客服配置（Day 59）。
 *
 * <p>★★ {@code apiKey} 为空时<b>整个模块走 mock 模式</b>（规则 + 真实工具调用），
 * 与短信验证码同一个思路：流程/接口/工具全真，只有「生成语言」这一步是替身。
 * 这样本地与 CI 都能测，配上一个 key 就切真模型，不改任何代码。
 *
 * <p>★ 默认走 OpenAI 兼容协议（DeepSeek 就是这套）：换 OpenAI / 通义 / 本地 vLLM
 * 只需要改 {@code AI_BASE_URL} / {@code AI_MODEL}，协议层不用动。
 */
@Data
@Component
@ConfigurationProperties(prefix = "mallx.ai")
public class AiProperties {

    /** OpenAI 兼容的 base url（不含 /chat/completions） */
    private String baseUrl = "https://api.deepseek.com/v1";

    /** 为空 = mock 模式；★ 只从环境变量注入，绝不写进配置文件 */
    private String apiKey = "";

    private String model = "deepseek-chat";

    /** 工具循环最多几轮（防止模型来回调工具停不下来） */
    private int maxToolRounds = 3;

    private int timeoutSeconds = 20;

    /** 单用户（游客按 IP）每分钟最多几次 */
    private int ratePerMinute = 20;

    /** Python AI 服务地址（FastAPI + LangChain）；为空时用 Java 内置的 LangChain4j/mock */
    private String serviceUrl = "";
}
