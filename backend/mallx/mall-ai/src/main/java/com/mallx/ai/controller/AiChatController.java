package com.mallx.ai.controller;

import com.mallx.ai.config.AiProperties;
import com.mallx.ai.dto.AiChatRequest;
import com.mallx.ai.service.AiChatService;
import com.mallx.ai.service.AiRateLimiter;
import com.mallx.ai.vo.AiChatReply;
import com.mallx.common.api.Result;
import com.mallx.common.exception.BusinessException;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * AI 客服（Day 59）。
 *
 * <p>★ <b>游客也能聊</b>：`SecurityConfig` 对 {@code POST /api/ai/chat} 精确放行，
 * 匿名请求在这里 {@code authentication == null}，服务层据此只允许问商品。
 *
 * <p>⚠️ 限流用「登录用户 id / 游客 IP」两个桶：游客之间共用一个桶会把正常用户一起限掉。
 *
 * <p>★ 为什么不在这里做流式：第一版先把「工具调用 + 安全边界」跑通；真实模型是同步返回，
 * 流式需要 provider 的 SSE 解析，属于下一步。前端的「逐字显示」是展示效果，不是传输流。
 */
@Tag(name = "AI 客服")
@RestController
@RequestMapping("/api/ai")
public class AiChatController {

    private final AiChatService aiChatService;
    private final AiRateLimiter rateLimiter;
    private final AiProperties props;

    public AiChatController(AiChatService aiChatService, AiRateLimiter rateLimiter, AiProperties props) {
        this.aiChatService = aiChatService;
        this.rateLimiter = rateLimiter;
        this.props = props;
    }

    @Operation(summary = "客服对话（游客可用，登录后可查订单/售后）")
    @PostMapping("/chat")
    public Result<AiChatReply> chat(Authentication authentication,
                                    HttpServletRequest request,
                                    @RequestBody @Valid AiChatRequest body) {
        Long userId = (authentication != null && authentication.getPrincipal() instanceof Long id) ? id : null;
        String bucket = userId != null ? "u:" + userId : "ip:" + clientIp(request);
        if (!rateLimiter.allow(bucket, props.getRatePerMinute())) {
            throw new BusinessException(429, "问得有点快，歇一会儿再试。");
        }
        return Result.ok(aiChatService.chat(userId, body));
    }

    /** 代理后面取真实客户端 IP；没有 XFF 就用直连地址 */
    private static String clientIp(HttpServletRequest request) {
        String xff = request.getHeader("X-Forwarded-For");
        if (xff != null && !xff.isBlank()) {
            return xff.split(",")[0].trim();
        }
        return request.getRemoteAddr();
    }
}
