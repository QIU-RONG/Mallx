# Day 79 · AI 客服流式输出（SSE）

## 做了什么

- 新增 POST /api/ai/chat/stream（	ext/event-stream），与同步接口同一套限流与游客放行；
- 事件协议：
  - event: delta + {"text":"..."} —— 按 8 字一片、18ms 间隔推送；
  - event: done + {"mock":bool,"tools":[...]}；
  - event: error + {"message":"..."}；
- 前端挂件优先走流式：先插入一条空 assistant 消息，边收边追加；**流不可用时自动退回同步接口**，
  用户无感（旧接口一行没改）；
- 流式计算仍复用 chat()（含工具调用），只是把「完整回答」按片推送。

## 验证

- SSE 实测：200 + 	ext/event-stream，11 个 delta + 1 个 done，拼接文本完整；
- 前端实测：点快捷问题后回答逐段出现，最终内容与同步接口一致；
- 主链路 e2e 40/40。

## 边界（诚实说明）

1. 这是**传输流**，不是 provider 的 token 流：工具调用需要完整一轮 tool_calls，
   真 token 流要等 provider SSE 解析支持（下一步）；
2. 流式失败不会自动重试，只提示；同步接口仍是兜底；
3. CompletableFuture.runAsync 用公共池 —— 单机演示够用，生产应换成有界线程池/反应式。
