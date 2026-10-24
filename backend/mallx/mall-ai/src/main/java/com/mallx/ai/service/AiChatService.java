package com.mallx.ai.service;

import com.mallx.ai.dto.AiChatRequest;
import com.mallx.ai.vo.AiChatReply;

/** AI 客服入口（Day 59） */
public interface AiChatService {

    /**
     * @param userId 当前登录用户；<b>游客为 null</b>（只能问商品，不能查订单）
     */
    AiChatReply chat(Long userId, AiChatRequest request);

    /**
     * 流式对话（Day 79）：先算出完整回答，再按片推给前端（SSE）。
     *
     * <p>★ 这是「传输流」而不是「模型 token 流」：工具调用需要完整一轮 tool_calls，
     * provider 的 token 流要等工具链路稳定后再做（见 docs/Day-79）。
     * 对用户的效果一样：回答会逐段出现，不必等整段生成完。
     */
    void stream(Long userId, AiChatRequest request, org.springframework.web.servlet.mvc.method.annotation.SseEmitter emitter);
}
