package com.mallx.ai.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.mallx.ai.config.AiProperties;
import com.mallx.ai.dto.ChatTurn;
import org.springframework.stereotype.Component;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

/**
 * 调用 Python AI 服务（FastAPI + LangChain，Day 108）。
 *
 * <p>只做转发：用户 token 原样透传给 Python，由 Python 工具回查 Java 的 C 端接口；
 * 模型与工具都在 Python 侧，Java 不保存 key。
 */
@Component
public class AiServiceClient {

    public record Reply(String text, List<String> tools, List<com.mallx.ai.vo.AiSource> sources, long elapsedMs) {
    }

    private final AiProperties props;
    private final ObjectMapper om = new ObjectMapper();
    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5)).build();

    public AiServiceClient(AiProperties props) {
        this.props = props;
    }

    public Reply chat(Long userId, String message, List<ChatTurn> history) throws Exception {
        ObjectNode body = om.createObjectNode();
        body.put("message", message);
        body.put("user_id", userId == null ? 0 : userId);
        ArrayNode arr = body.putArray("history");
        if (history != null) {
            for (ChatTurn t : history) {
                if (t == null || t.getContent() == null) {
                    continue;
                }
                arr.addObject().put("role", t.getRole()).put("content", t.getContent());
            }
        }
        String url = props.getServiceUrl().replaceAll("/$", "") + "/chat";
        HttpRequest.Builder b = HttpRequest.newBuilder(URI.create(url))
                .timeout(Duration.ofSeconds(props.getTimeoutSeconds() + 5))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(om.writeValueAsString(body)));
        String auth = currentAuthorization();
        if (auth != null) {
            b.header("Authorization", auth);
        }
        HttpResponse<String> resp = http.send(b.build(), HttpResponse.BodyHandlers.ofString());
        if (resp.statusCode() != 200) {
            throw new IllegalStateException("AI 服务返回 " + resp.statusCode());
        }
        JsonNode json = om.readTree(resp.body());
        List<String> tools = new ArrayList<>();
        json.path("tools").forEach(n -> tools.add(n.asText()));
        List<com.mallx.ai.vo.AiSource> sources = new ArrayList<>();
        json.path("sources").forEach(n -> sources.add(new com.mallx.ai.vo.AiSource(
                n.path("source").asText(""), n.path("heading").asText(""))));
        return new Reply(json.path("reply").asText(""), tools, sources, json.path("elapsed_ms").asLong(0));
    }

    private String currentAuthorization() {
        if (RequestContextHolder.getRequestAttributes() instanceof ServletRequestAttributes attrs) {
            return attrs.getRequest().getHeader("Authorization");
        }
        return null;
    }
}
