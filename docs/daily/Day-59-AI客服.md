# Day 59 · AI 客服（售前导购 + 售后查询）

> 需求原话：**「我想添加一个 ai 客服模块，要怎么做」** → 讨论后确定「售前 + 售后都要」。
> 设计稿：[`docs/superpowers/specs/2026-10-23-mallx-ai-customer-service-design.md`](../superpowers/specs/2026-10-23-mallx-ai-customer-service-design.md)

---

## 0. 结论速览

| 项 | 结果 |
|---|---|
| 新模块 | `mall-ai`（依赖 product / order / aftersale，只被 server 依赖） |
| 接口 | `POST /api/ai/chat`（游客可调） |
| 工具 | `search_products` / `get_my_orders` / `get_my_refunds`，**全部只读**，userId 只从 token 取 |
| 模型 | OpenAI 兼容协议，默认 DeepSeek；`AI_API_KEY` 为空时走 **mock**（规则 + 真实工具） |
| 前端 | 右下角悬浮客服 `AiChat.vue`：快捷问题、工具回执、开发模式标记 |
| 验证 | 后端单测 **5/5**；`day59-ai-verify.py` **11/11**；主链路 e2e **40/40**；lint/build 通过 |

---

## 1. 为什么是「工具调用」而不是「把数据塞进 prompt」

```
用户问题 → 模型决定调哪个工具 → 后端用【当前 token】执行 → 结果回喂模型 → 模型组织语言
```

- 商品价格、订单状态这类事实**必须实时**；写死进 prompt 第二天就是错的。
- 模型只负责“怎么说”，不负责“是什么”。工具没返回的内容，prompt 明令禁止编造。
- **工具不接受 userId 入参**：让模型决定查谁 = 把越权交给一个会被提示注入的组件。
  归属只在服务端从 token 取，这是唯一可靠的位置。
- 第一版**零写操作**：不下单、不退款、不改地址。需要行动时，回答只给页面入口。

## 2. 三条路径

| 场景 | 行为 |
|---|---|
| 游客问商品 | 允许；`search_products` 正常执行 |
| 游客问订单/售后 | 工具被调用但返回「未登录」，回答提示先登录 —— **不猜、不静默跳过** |
| 登录后问订单/售后 | 只查 token 对应用户的最近 5 条 |

## 3. mock 模式（没有 key 也能跑）

`AI_API_KEY` 为空时不用模型：规则判意图（退款/订单/商品/寒暄）→ 调**真实工具** → 模板化回答。

★ 与短信验证码同一个思路：存储、流程、接口、工具全真，只有「生成语言」是替身。
★ CI 与本地默认走这条，接上 key 后同一套代码走真实模型，**验收用例不用改**（断言的是工具与事实，不是文风）。

## 4. 安全边界（写进代码，而不是只写进 prompt）

- `history` 只接受 `user` / `assistant`，**客户端塞 `system` 一律丢弃**（防提示注入）；
- system prompt 明确禁止：透露提示词、查他人数据、编造价格/状态、执行写操作；
- 但真正的防线是工具层：没有 userId 参数、没有写操作 —— 即使模型被说服，它也做不到；
- 限流：同一用户 / 游客 IP 每分钟 20 次，超限返回业务码 429（HTTP 200）；
- 上游异常不原样回传（可能含网关内网地址），统一兜底文案。

★ 已知取舍：游客限流信任 `X-Forwarded-For`。生产要求前面只有 Caddy（部署物料里就是这样），
若应用直接暴露公网，这个头可被伪造 —— 记在这里，不假装它没有。

## 5. 怎么接真模型

```bash
set AI_API_KEY=sk-xxxx          # 或 xAI / OpenAI / 通义的 key
set AI_BASE_URL=https://api.deepseek.com/v1
set AI_MODEL=deepseek-chat
# 重启后端即可；代码零改动
```

工具循环最多 3 轮；模型要求调工具时才调，不需要时直接回答。

## 6. 验证

| 项 | 结果 |
|---|---|
| `mall-ai` 单测 | **5/5**（游客不越权 / 商品意图 / 售后意图 / 寒暄不调工具 / history 注入被过滤） |
| `day59-ai-verify.py` | **11/11**（见下） |
| `day56-local-e2e.py` | **40/40**（主链路无回归） |
| 前端 | lint 0 / 15 单测 / build |

`day59-ai-verify.py` 覆盖：游客商品（工具真调、回答含库里商品）→ 游客订单（要求登录）
→ 登录订单（订单号与库一致）→ history 注入（不 500、回答不变）→ 限流（第 21 次起 429）。

## 7. 途中踩到的坑

1. **Spring Boot 4 没有默认的 `ObjectMapper` Bean** —— 启动直接 `No qualifying bean of type ObjectMapper`。
   改用 `new ObjectMapper()`（只用它建 JSON/读 JSON，不需要全局配置）。
2. **PowerShell 的 `Invoke-RestMethod` 发中文 JSON 会乱码**（无 charset 时按 ANSI 编码），
   导致接口“像坏了”。验证改用 Python `ensure_ascii=False` + UTF-8。
3. **`Get-Content -Raw | Set-Content` 改测试文件把中文写成乱码**，javac 报「非法字符」。
   该用文件写入工具，别用 shell 管道改源码。
4. **jar 被运行中的后端锁住**，`mvn package` 报 `Unable to rename`。先停进程再打包。
5. **开发模式提示重复**：后端拼进正文 + 前端还显示 meta 标签。改为一处（前端 meta）。
6. **dev server 缓存了旧 App.vue**：新增 <AiChat /> 后页面里没有挂件，而 prod build 正常。/src/App.vue 返回的内容已含 import，但长时间运行的 Vite 实例模块图没失效（写文件是原子替换，Windows 下 watcher 可能漏事件）⇒ **重启 dev server 即恢复**。判断方法：CDP 里 document.querySelector('.fab') 为 null 且控制台无报错。

## 8. 没做的

1. **真实模型联调**：本机没有 key，只验到 mock 链路；协议与工具循环已按 OpenAI 兼容实现。
2. **流式输出**：当前是同步返回 + 前端打字机效果；真流式需要解析 provider 的 SSE，属于下一步。
3. **RAG / 向量检索**：商品量小，用现有搜索接口当工具足够；商品上千或加知识库（退换货规则文档）时再引入。
4. **人工转接**：没做工单/坐席，回答里只给页面入口。
5. 管理端未做（不需要）。
## 9. 增补（同日）：挂件可拖动

需求：**「我想悬浮客服是可移动的」**。

- 用 Pointer Events 实现拖动（鼠标 / 触屏同一套），	ouch-action: none 防止拖动时页面滚动；
- **拖过 4px 才算移动**，否则仍按点击处理 —— 否则用户永远点不开面板；
- 位置存 localStorage（mall_ai_fab_pos），刷新后保持；窗口缩放时把位置钳回可视区；
- 对话面板跟随按钮：优先出现在按钮上方，上面放不下就放下面，左右按视口钳制；
- 实测（CDP 合成指针事件）：拖到 (680,380) → localStorage 保存 → 刷新后 style.left/top 仍是 680/380；同一按钮短按仍能打开面板。