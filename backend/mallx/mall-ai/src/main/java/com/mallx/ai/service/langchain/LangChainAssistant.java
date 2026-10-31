package com.mallx.ai.service.langchain;

import dev.langchain4j.service.SystemMessage;
import dev.langchain4j.service.UserMessage;

/** LangChain4j 的 AiService 接口：一句话进、一句话出（工具由 AiServices 自动编排） */
public interface LangChainAssistant {

    @SystemMessage("""
            你是 MallX 商城的在线客服「小 M」。
            只回答商品咨询、订单状态、售后进度；不编造订单号/金额/物流，不承诺未发生的事。
            涉及用户数据时必须调用工具，禁止根据提问内容猜测。
            """)
    String chat(@UserMessage String message);
}
