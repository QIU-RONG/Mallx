package com.mallx.ai.service.langchain;

import com.mallx.ai.config.AiProperties;
import com.mallx.ai.dto.ChatTurn;
import com.mallx.ai.service.AiTools;
import dev.langchain4j.model.chat.ChatModel;
import dev.langchain4j.model.openai.OpenAiChatModel;
import dev.langchain4j.service.AiServices;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;

/**
 * LangChain4j 编排层（Day 107）。
 *
 * <p>没有 API Key 时不会调用本类（见 AiChatServiceImpl）；构建模型要传 key，
 * 所以这里按需构建并缓存一个模型实例。
 */
@Service
public class LangChainService {

    private final AiProperties props;
    private final AiTools tools;
    private volatile ChatModel model;

    public LangChainService(AiProperties props, AiTools tools) {
        this.props = props;
        this.tools = tools;
    }

    /** @return 模型文本；{@code usedTools} 回填本轮实际调用的工具名 */
    public String chat(Long userId, String message, List<ChatTurn> history, List<String> usedTools) {
        List<String> used = new ArrayList<>();
        LangChainTools tool = new LangChainTools(userId, tools, used);
        LangChainAssistant assistant = AiServices.builder(LangChainAssistant.class)
                .chatModel(model())
                .tools(tool)
                .build();
        String text = assistant.chat(prompt(message, history));
        usedTools.addAll(used);
        return text;
    }

    private ChatModel model() {
        if (model == null) {
            synchronized (this) {
                if (model == null) {
                    model = OpenAiChatModel.builder()
                            .apiKey(props.getApiKey())
                            .baseUrl(props.getBaseUrl())
                            .modelName(props.getModel())
                            .timeout(java.time.Duration.ofSeconds(props.getTimeoutSeconds()))
                            .build();
                }
            }
        }
        return model;
    }

    private String prompt(String message, List<ChatTurn> history) {
        if (history == null || history.isEmpty()) {
            return message;
        }
        StringBuilder sb = new StringBuilder("对话历史：\n");
        for (ChatTurn turn : history) {
            sb.append("user".equals(turn.getRole()) ? "用户" : "客服").append("：")
                    .append(turn.getContent()).append('\n');
        }
        sb.append("当前问题：").append(message);
        return sb.toString();
    }
}
