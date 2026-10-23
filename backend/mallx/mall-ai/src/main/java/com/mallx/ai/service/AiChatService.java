package com.mallx.ai.service;

import com.mallx.ai.dto.AiChatRequest;
import com.mallx.ai.vo.AiChatReply;

/** AI 客服入口（Day 59） */
public interface AiChatService {

    /**
     * @param userId 当前登录用户；<b>游客为 null</b>（只能问商品，不能查订单）
     */
    AiChatReply chat(Long userId, AiChatRequest request);
}
