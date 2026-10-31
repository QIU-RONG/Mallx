package com.mallx.ai.service.langchain;

import com.mallx.ai.service.AiTools;
import dev.langchain4j.agent.tool.Tool;

import java.util.List;

/**
 * 暴露给模型的只读工具（Day 107）。
 *
 * <p>★ 用户身份由构造注入，工具签名里<b>没有 userId</b> —— 与手写版本同一条边界：
 * 模型无法指定查谁的数据，即使被提示词注入也只能查当前登录用户。
 */
public class LangChainTools {

    private final Long userId;
    private final AiTools delegate;
    private final List<String> used;

    public LangChainTools(Long userId, AiTools delegate, List<String> used) {
        this.userId = userId;
        this.delegate = delegate;
        this.used = used;
    }

    @Tool("按关键词搜索在售商品，返回名称、价格与 id")
    public String searchProducts(String keyword) {
        used.add("searchProducts");
        return delegate.searchProducts(keyword);
    }

    @Tool("查询当前登录用户自己的订单列表（无需参数）")
    public String myOrders() {
        used.add("myOrders");
        return delegate.myOrders(userId, null);
    }

    @Tool("查询当前登录用户自己的售后/退款进度（无需参数）")
    public String myRefunds() {
        used.add("myRefunds");
        return delegate.myRefunds(userId);
    }
}
