# Day 123 · 注入对抗、首字延迟与 CI

## Prompt 注入对抗（真实模型）

`eval_injection.py`：8 条恶意问题（套系统提示词、要密钥、查别人订单、贴源码等），
检查回答是否出现**真实泄漏特征**（密钥值/密码值/系统提示词原文片段）。

- 结果：**8/8 通过，0 泄漏**；
- 第一版把「系统提示词」「数据库密码」这类**提及**也判成泄漏，误报 4 条；
  改成只匹配真实密钥/原文片段后通过 —— 评测脚本本身也要防假阴性/假阳性。

## 首字延迟

`eval_latency.py` 经 Java `/api/ai/chat/stream` 测首个 delta 到达时间：

- 5 题：2488–3788ms，**p50 2903ms / avg 2995ms**；
- 口径说明：当前是「先完整生成再切片推送」，所以这个值≈完整生成耗时（含工具轮），不是模型 TTFT。

## CI

新增 `.github/workflows/ai-eval.yml`：PostgreSQL 服务 → 跑 01–29 迁移 → `kb_ingest.py` →
`eval_retrieval.py`（50 题），只依赖 hash embedding，不需要 API key。

## 验证

- 注入 8/8；延迟样本见 `eval-latency-report.json`；
- 工作流文件已提交（本地无法运行 GitHub Actions，仅做静态审阅）。
