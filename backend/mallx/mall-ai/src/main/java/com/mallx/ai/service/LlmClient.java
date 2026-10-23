package com.mallx.ai.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.mallx.ai.config.AiProperties;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

/**
 * OpenAI 兼容协议的模型客户端（Day 59）。
 *
 * <p>★ 不引 SDK：只用到「POST 一个 JSON、读回 choices[0].message」这两件事，
 * 手写 HttpClient 比多背一个 SDK 的版本兼容更省心。DeepSeek / OpenAI / vLLM 都是这套协议。
 *
 * <p>⚠️ 超时是硬要求：客服是<b>同步</b>调用，模型卡住会占住 Tomcat 线程 ——
 * 默认 20s，超时后由上层返回兜底文案，不把异常原样抛给用户。
 */
@Component
public class LlmClient {

    private final AiProperties props;
    private final ObjectMapper om;
    private final HttpClient http;

    public LlmClient(AiProperties props) {
        this.props = props;
        // ★ 自己 new 一个：Spring Boot 4 的 web 组件并没有默认暴露 ObjectMapper Bean
        //   （启动时报 "No qualifying bean of type ObjectMapper" 就是这里）。
        //   我们只用它做「建 JSON / 读 JSON」，不需要全局配置。
        this.om = new ObjectMapper();
        this.http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(Math.max(3, props.getTimeoutSeconds() / 2)))
                .build();
    }

    /** @return choices[0].message（含 content / tool_calls） */
    public JsonNode complete(ArrayNode messages, ArrayNode tools) throws Exception {
        ObjectNode body = om.createObjectNode();
        body.put("model", props.getModel());
        body.set("messages", messages);
        body.set("tools", tools);
        body.put("tool_choice", "auto");
        body.put("temperature", 0.3);
        body.put("max_tokens", 700);

        HttpRequest req = HttpRequest.newBuilder()
                .uri(URI.create(trimSlash(props.getBaseUrl()) + "/chat/completions"))
                .timeout(Duration.ofSeconds(props.getTimeoutSeconds()))
                .header("Content-Type", "application/json")
                .header("Authorization", "Bearer " + props.getApiKey())
                .POST(HttpRequest.BodyPublishers.ofString(om.writeValueAsString(body), StandardCharsets.UTF_8))
                .build();

        HttpResponse<String> resp = http.send(req, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        if (resp.statusCode() / 100 != 2) {
            throw new IllegalStateException("LLM HTTP " + resp.statusCode() + ": " + truncate(resp.body(), 300));
        }
        JsonNode root = om.readTree(resp.body());
        JsonNode choices = root.path("choices");
        if (!choices.isArray() || choices.isEmpty()) {
            throw new IllegalStateException("LLM 返回为空");
        }
        return choices.get(0).path("message");
    }

    private static String trimSlash(String s) {
        return s.endsWith("/") ? s.substring(0, s.length() - 1) : s;
    }

    private static String truncate(String s, int max) {
        if (s == null) {
            return "";
        }
        return s.length() <= max ? s : s.substring(0, max) + "...";
    }
}
