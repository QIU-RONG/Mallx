# Day 111 · AI 会话记忆、token 统计与回答评测

## 会话记忆

- 迁移 27：i_conversations + i_messages（含 prompt/completion tokens 列）；
- Python /chat 接受 conversation_id：有则从库里取最近 10 条历史，没有则新建；
  回答后落库 user + assistant 两条，返回 conversation_id；
- Java：AiChatRequest.conversationId → AiServiceClient 透传 → AiChatReply.conversationId；
  SSE done 事件同样携带 conversationId；
- 前端：localStorage['mallx_ai_conv'] 保存会话 id，刷新后继续同一段对话；
- 验证：两轮对话返回同一 conversationId，/kb/stats 显示 conversations=1、messages=4。

## token 统计

- ChatOpenAI(stream_usage=True) + UsageTracker 回调收集 prompt/completion_tokens；
  假模型不返回 usage，所以联调时 tokens=0（预期）；真实模型会写入 i_messages 并回传；
- /kb/stats 附带 conversations/messages/tokens 汇总；前端气泡显示 N tokens（>0 时）。

## 回答评测

- eval/eval_answers.py：10 条政策问题 → 调 /chat，检查回答非空、引用来源在知识库中存在；
- 本次（假模型）结果：cited=10/10, invalid_refs=0, citation_rate=1.0；
  ⚠️ 假模型对每个问题都给固定回答，**只能证明评测链路通**，回答质量需配真实 key 后再跑；
- 报告：i-service/eval/eval-answers-report.json。

## 验证汇总

- 前端 lint/build、后端 package、Java(8082)→Python 会话复用均通过；默认 8081（mock）e2e 40/40。
