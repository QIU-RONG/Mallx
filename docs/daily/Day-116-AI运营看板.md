# Day 116 · AI 运营看板（调用量 / token / 延迟 / 拒答）

## 数据

- 迁移 28：i_messages 增加 elapsed_ms、efusal 与时间索引；
- Python memory.append() 落库耗时与拒答标记；GET /ai/stats 提供聚合。

## 管理端

- 新接口 GET /api/admin/ai/stats（权限 dashboard:overview）：
  calls / todayCalls / promptTokens / completionTokens / avgElapsedMs / refusals / refusalRate；
- 直接查 i_messages（与 Python 同一张表），不依赖 AI 服务在线；
- 新页面「AI 运营」（/ai-ops）：累计/今日调用、平均耗时、拒答率、两类 token、拒答次数；
- 菜单对拥有 dashboard:overview 的角色可见。

## 验证

- 真实模型调用后 	okens=730，/api/admin/ai/stats 返回
  calls=80, promptTokens=35720, completionTokens=4088, avgElapsedMs=2321；
- 前端 lint / build 通过；接口 200（修复了 ound(avg()) FILTER 的语法错误）。
