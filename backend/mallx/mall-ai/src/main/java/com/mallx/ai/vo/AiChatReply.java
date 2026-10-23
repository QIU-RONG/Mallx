package com.mallx.ai.vo;

import lombok.AllArgsConstructor;
import lombok.Data;

import java.util.List;

/**
 * 客服回答（Day 59）。
 * <p>★ {@code tools} 里是<b>本轮真正执行过的工具名</b>，不是「模型声称调过」——
 * 排查「它怎么知道我的订单」时，这一列就是证据。
 */
@Data
@AllArgsConstructor
public class AiChatReply {

    private String reply;

    /** mock / llm —— 前端据此显示「开发模式」标记 */
    private String mode;

    /** 本轮执行过的工具（可能为空） */
    private List<String> tools;
}
