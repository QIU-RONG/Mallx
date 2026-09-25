# Day 27 — 性能基线：索引到底有没有被用上（EXPLAIN 复盘）

> 本日**没有改一行 Java、没有动一个 DDL、没有加一个索引**。
> 做的是把「本项目用了三件索引」从**声明**变成**证据**，并且**先造出能让索引有胜算的样本**。

---

## 一、为什么是这一步（决策依据）

V1.0 收口之后有四条路可走，本日的选择有明确依据：

| 候选 | 判断 |
|---|---|
| **① CI 首跑盯日志** | **待办**（提交已推送，只能上 runner 看）—— 不占一个 Day |
| **② V1.1 Redis + RabbitMQ** | ★ 原本的理由是「订单超时不会自动关单、库存预占不释放」——**这个理由本日被证伪**，见 §二 |
| **③ 性能基线（本日选的）** | 项目第一条约束是「**用关系库把该做的事做完**」。在引入中间件之前，必须先回答「关系库到底够不够用」——而这个问题**今天一条数据都没有** |
| ④ 前端界面 | 属**需求决策**（要不要改 V1.0 范围），不是技术缺口 |

★ 判据：**在「加中间件」与「先量一下」之间，永远先量。**
否则很容易把「引入 Redis」当成成就感，而不是解法 —— 而 `docs/perf-report.md`
现有的并发证据全部来自**功能正确性压测**（20 线程抢 10 件库存），
**没有一条 `EXPLAIN`**。索引是不是真的被用上，此前无人验证。

---

## 二、★ 先纠正一个前提错误：超时关单**早已实现**

本日开工前的记录（`.workbuddy/memory`）把 V1.1 的理由写成
「订单**超时未支付不会自动关单**、库存预占**不释放**」。**这是错的。** 实证：

| 证据 | 内容 |
|---|---|
| `mall-order/.../task/OrderTimeoutTask.java` | `@Scheduled(fixedDelay = 60_000)` + `TIMEOUT_MINUTES = 2` |
| `MallXApplication.java` | `@EnableScheduling`（Day 14 第 3 步已加） |
| `OrderService#cancelTimeoutOrders(int)` | 真正的逻辑；★ 定时任务**没有 SecurityContext**，所以必须走「系统视角」独立入口，不能复用用户视角的 `cancel(userId, orderId)` —— 这是**权限模型的分层**，不是省代码 |
| `day14-timeout-verify.py` | **21 条断言全 PASS**，其中包含「没人调接口，订单自己翻状态」「等待时长 > 阈值且 <= 阈值 + 一个轮询间隔」「再跑一轮 `cancelled_at` 不变」「业务守恒 drift = 0」 |

⇒ **V1.0 的功能面是真的齐了。** 这一条纠正直接改变了下一步的排序：
V1.1 不再有「功能缺口」这个理由，只剩「轮询 vs 事件驱动」的**性能/架构**理由 ——
而那正是必须先有性能数据的理由。

★ 一般化：**「记忆里的缺口」不等于「代码里的缺口」。** 动手前先 grep 一遍，
否则会把一个已经做完的事再排进路线图。

---

## 三、方法：先让样本有区分度，再谈索引

### 3.1 要打破的那句话

`docs/perf-report.md` §五 写着：

> ★ 小表上「看不到索引」不是做错了 —— `EXPLAIN` 在只有 5 行的 `products` 上**一定选 `Seq Scan`**。

这句话**是对的**，但它同时让「索引没被用上」**永远无法被证伪**：
5 行时是「正常」，30 万行时也能被同一句话糊过去。

★ 判据（与 backlog L1 的「样本量陷阱」同源）：
**要验「索引有没有被用上」，样本必须大到让索引有胜算。**

### 3.2 做法（★ 零副作用）

```
临时库 mallx_perf_probe（与 day25-sql-strict-check.py 同一套路）
  → 灌 01→14（与 initdb 同序，ON_ERROR_STOP=1）
  → 造数：products 3 万 / product_skus 6 万 / orders 3 万 / order_items 3 万
          / inventory_logs 6 万 / reviews 2 万
  → ANALYZE                       ★ 不做这步 pg_class.reltuples 还是 0，计划器只能瞎猜
  → 12 条查询逐条 EXPLAIN (ANALYZE, BUFFERS)
  → DROP DATABASE                 ★ 开发库一个字节都不碰
```

### 3.3 查询从哪来

**从 `*Mapper.xml` 与 Service 逐条转录**，不是自己编的 SQL。
每条都在报告里标出对应的代码位置，便于复核。

---

## 四、查询集与「设计预期」

★ 断言**对着设计写**，并且**分两类** —— 这是本日最重要的设计：

| 类 | 含义 | 为什么必须有 |
|---|---|---|
| **正向** | 该索引就是为这条查询建的 ⇒ 计划里**必须出现**该索引 | 直接验「索引有效」 |
| **反向对照** | 这条查询**设计上就该全表扫**（前导 `%` 废掉 B-tree、`OR` 挡住索引、低选择性列）⇒ 计划**必须**是 `Seq Scan` | 没有这一类，就无法区分「索引没用」与「**索引被查询写法挡住了**」 |

| ID | 查询 | 设计预期 | 理由 |
|---|---|---|---|
| Q1 | C 端商品列表 `status = 1` | **SEQ**（反向） | `status` 是低选择性列（命中 ~100% 行），索引无胜算 |
| Q2 | C 端列表按 `category_id` | `idx_products_category_id` | 该索引就是为它建的 |
| Q3 | `countByCategoryId`（含软删） | `idx_products_category_id` | 删除分类的引用校验 |
| Q4 | 搜索：全文 `search_vector @@` | `idx_products_search`（GIN） | Day 19 的核心资产 |
| Q5 | 搜索：中文兜底（`ILIKE` 三列 **+ OR**） | **SEQ**（反向） | ★ 前导 `%` 废掉索引；且 `OR` 会把可用的 trgm 索引一起挡掉 |
| Q6 | 搜索：**单列** `ILIKE`（去掉 OR） | `idx_products_name_trgm` | ★ 与 Q5 成对照：证明「是 OR 挡住的，不是索引不存在」 |
| Q7 | 搜索：属性筛选 `attributes @>` | `idx_product_skus_attributes`（GIN） | Day 19 的第三件索引 |
| Q8 | 订单列表按 `user_id` | `idx_orders_user_id` | — |
| Q9 | ★ **超时关单扫描**（每 60 秒一次） | `idx_orders_status` | 这是**唯一一条按分钟级频率自动执行的查询**，最该被验证 |
| Q10 | 订单明细按 `order_id` | `idx_order_items_order_id` | — |
| Q11 | 库存流水按 `sku_id` 倒序 | `idx_inventory_logs_sku_id` | 管理端流水页 |
| Q12 | 评价按 `product_id` | `idx_reviews_product_id` | — |

---

## 五、本日不做什么（★ 划清边界）

- **不改索引、不改 SQL、不改代码。** 本日只产出**证据**。
  索引怎么调，等 §六 的数字出来再定 —— 否则就是「先改再找理由」。
- **不引入任何中间件。**

---

## 六、实测

脚本：`backend/loadtest/day27-explain-audit.py` → `day27-explain-audit-report.txt`
结果：**38 / 38 passed**，`VERDICT: OK`，**连跑三次结果一致**。
全程在**临时库** `mallx_perf_probe` 里做，跑完 `DROP DATABASE` —— 开发库零改动。

### 6.1 环境与规模

| 项 | 值 |
|---|---|
| 补丁 | 01→14 按序，`ON_ERROR_STOP=1`，全部 `rc=0` |
| 分类 / 用户 | 300 / 5000（★ 专门造出选择性） |
| products / product_skus | 30005 / 60007 |
| orders / order_items | 30000 / 30000 |
| inventory_logs / reviews | 60000 / 20000 |
| 稀有词命中率 | `iphone` **31 / 30000**（0.1%） |
| `PENDING_PAYMENT` 占比 | **300 / 30000**（1%） |
| 索引整理 | **`VACUUM (ANALYZE)`** ← 见 6.4，这一步不是可选的 |

### 6.2 逐条结果（取一次代表性运行；耗时会小幅波动）

| ID | 查询 | 设计预期 | 实得计划 | 耗时 |
|---|---|---|---|---|
| Q1 | C 端列表 `status = 1` | **不得用** `idx_products_status` | `products_pkey` 反向扫 | 0.2 ms |
| Q2 | 列表按 `category_id`（无 LIMIT） | 用 `idx_products_category_id` | ✅ 命中 | 1.7 ms |
| Q3 | `countByCategoryId` | 用 `idx_products_category_id` | ✅ 命中 | 0.4 ms |
| **Q5** | ★★ **真实 `searchProducts`（含 OR 兜底）** | **不得用** `idx_products_search` | ❌ **`Seq Scan on products`** | **68.5 ms** |
| Q6 | 中文兜底（ILIKE 三列 + OR） | **不得用** `idx_products_name_trgm` | ❌ `Seq Scan` | 15.4 ms |
| Q7 | **单列** ILIKE（去掉 OR） | 用 `idx_products_name_trgm` | ✅ 命中 | 0.7 ms |
| Q8a | 属性筛选（EXISTS 驱动） | 用 `idx_product_skus_attributes` | ✅ 命中（见 6.3） | 3.4 ms |
| Q8b | 属性筛选（从 SKU 侧查） | 用 `idx_product_skus_attributes` | ✅ 命中 | 2.4 ms |
| Q9 | 订单列表按 `user_id` | 用 `idx_orders_user_id` | ✅ 命中 | 0.6 ms |
| Q10 | ★ **超时关单扫描**（每 60 秒） | 用 `idx_orders_status` | ✅ 命中 | 1.1 ms |
| Q11 | 订单明细按 `order_id` | 用 `idx_order_items_order_id` | ✅ 命中 | 0.3 ms |
| Q12 | 库存流水按 `sku_id` 倒序 | 用 `idx_inventory_logs_sku_id` | ✅ 命中 | 0.4 ms |
| Q13 | 评价按 `product_id` | 用 `idx_reviews_product_id` | ✅ 命中 | 0.3 ms |
| R1 | 列表按分类 **+ `ORDER BY id DESC LIMIT 10`** | （探针） | `products_pkey` 反向扫 | 1.4 ms |
| R2 | **纯**全文（无 OR） | （探针） | ✅ `idx_products_search` | 1.3 ms |

### 6.3 ★★★ 三个真发现（都不是「索引坏了」）

**① 全文 GIN 索引在生产形状下等于没用。**
`searchProducts` 的 `WHERE` 是
`(search_vector @@ ... OR name ILIKE ... OR subtitle ILIKE ... OR description ILIKE ...)`。
后两支 ILIKE 的列**没有索引** ⇒ 计划器无法拼出 `BitmapOr` ⇒ 只能全表扫。
**Q5 与 R2 是同一条 SQL 加/减一个 OR**：

| | 计划 | 耗时 |
|---|---|---|
| R2（纯全文） | `idx_products_search`（GIN） | **1.3 ms** |
| Q5（真实形状，含 OR） | `Seq Scan on products` | **68.5 ms** |

⇒ **索引是好的，挡住它的是查询写法。** 3 万行上差 **50 倍**。
★ 这也解释了为什么 Day 19 之后一直没觉得搜索慢：那时 `products` 只有 5 行。

**② `idx_products_status` 是一个死索引。**
`status = 1` 命中 99% 的行，任何计划器都不会为它走索引 —— 反向对照 Q1 成立。
它在 `02-index.sql` 里躺着，从未被选中过。

**③ `idx_products_category_id` 只在「不带 LIMIT」时才被用上。**
C 端列表真实形状是 `ORDER BY id DESC LIMIT 10`（`pageProducts` 里的 `orderByDesc(id)`），
计划器改用 PK 反向扫 + 过滤，**分类索引不被选中**（探针 R1）。
只有 `countByCategoryId`（Q3，无 LIMIT）才用得上它。

**★ 一个意外的好消息**：Q8a 我原本断言「EXISTS 从 product 侧驱动 ⇒ 用不上 GIN」，
**实测把它否掉了** —— 计划器主动把 EXISTS **反写成从 SKU 侧驱动**
（先 GIN 扫出 32 个黑色 SKU，再按 PK 取商品）。**是我的预期错了，不是计划器错了。**

### 6.4 ★★ 一段弯路：计划「反复翻转」的真因

第 5–7 轮跑的时候，Q4/R2/Q8b 的计划在 **GIN 与 Seq Scan 之间来回跳**。
我当时的解释是「处于计划器临界区 + 统计噪声」——**这个解释是错的**。

看 `BUFFERS` 才找到真因：GIN 扫 32 行要 **13.3 ms / 298 次 buffer 命中**（正常应 ~19 次）。
因为**批量灌完数之后没 `VACUUM`**，GIN 的 `fastupdate` **待处理列表**里还堆着几万条：

| | GIN 扫描成本 | 结果 |
|---|---|---|
| 灌数后直接 `ANALYZE` | `cost=1266`，13.3 ms | 计划器**放弃索引** → Seq Scan |
| 改成 `VACUUM (ANALYZE)` | `cost=21.4`，0.9 ms | 计划器**用索引** |

⇒ 判据：**现象不稳定时，先怀疑「被测对象处于未整理状态」，再怀疑「它本来就不确定」。**
后者更省事，但通常是把**测量装置的脏**当成了**系统的性质**。

---

## 七、结论与下一步

### 7.1 索引现状（12 条查询覆盖的 8 个索引）

| 索引 | 结论 |
|---|---|
| `idx_products_search`（GIN） | ⚠️ **有效但生产形状下用不上**（被 OR 挡住） |
| `idx_products_name_trgm` | ⚠️ 同上（被 OR 挡住）；单列查询才生效 |
| `idx_products_category_id` | ⚠️ 仅在**不带 LIMIT** 的查询里生效 |
| `idx_products_status` | ❌ **死索引**（低选择性，从不被选中） |
| `idx_product_skus_attributes`（GIN） | ✅ 有效（含 EXISTS 被反写的情形） |
| `idx_orders_user_id` / `idx_orders_status` | ✅ 有效 |
| `idx_order_items_order_id` / `idx_inventory_logs_sku_id` / `idx_reviews_product_id` | ✅ 有效 |

**V1.0 的索引总体是健康的** —— 但「建了索引」与「查询用得上索引」是两件事，
本日之前没有任何证据区分它们。

### 7.2 下一步的候选动作（★ 本日**不改**，留作决策）

按性价比排序，都属于「小改动 + 可测量」：

1. **让全文检索真正走上索引**（唯一有量级收益的一条）：
   三种改法各有取舍 ——
   (a) 给 `subtitle` / `description` 也加 `pg_trgm` 索引，让 `BitmapOr` 成立；
   (b) 把 OR 拆成 `UNION`，让每支各走各的索引；
   (c) 砍掉兜底、由应用层兜。
   ⚠️ 但 Day 20 的 L3 教训还立着：**改召回范围前先问「哪些断言是靠『命不中』成立的」**。
2. **删掉 `idx_products_status`**：零命中，还占写入成本。★ 但先确认没有别的查询依赖它。
3. **把性能审计纳入 CI**：`day27-explain-audit.py` 已经是幂等 + 零副作用的临时库脚本，
   可以直接挂进流水线，让「索引有没有被用上」变成每次 push 都验的事。

★ 本日没有得出「要不要上 Redis / MQ」的结论 —— 但得到了一个**更重要的**结论：
**当前最贵的一条查询（68.5ms）是一个纯 SQL 写法问题，不是缺中间件。**
先把 1 做掉再谈中间件，才不是在用新组件掩盖旧问题。
