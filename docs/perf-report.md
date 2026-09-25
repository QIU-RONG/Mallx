# MallX 性能与正确性报告

> **口径声明**：本文所有数字都取自 `backend/loadtest/` 下的脚本与它们生成的 `*-report.txt`，
> 不来自记忆或估算。报告文件的最后修改时间即取证时间。
> 每节末尾给出复现命令；脚本自带清理，可重复执行。

MallX V1.0 没有单元测试框架，取而代之的是 **60+ 个端到端验收脚本**：
全部打**真实 HTTP**，并用 `docker exec psql` **直查数据库对账**（不信接口自报），
跑完自动回到跑前状态。

---

## 一、并发正确性：不是「看起来没超卖」，是每一次写入都留了签名

并发缺陷的特点是**单线程下 100% 正确**，所以只能靠压测 + 反证来证明。
两个实验都采用「主组 + 对照组」：主组用正式实现，对照组把实现换成「先查后改」，
**必须亲眼看见它坏掉** —— 只有对照组成立，主组全绿才说明问题（否则只是没测到）。

### 1.1 并发下单：20 线程抢 10 件库存

装置：`day12-concurrent-order.py` + `day12-loadtest-setup.sql`（20 个独立账号，审计用 DB 触发器）

| 判据 | 主组（条件 UPDATE） | 对照组（先查后改） |
|---|---|---|
| 成功订单数 | **恰好 10** | **20（全部成功，一单没拒）** |
| 实际卖出 / 实际扣减 | 10 / 10 | **20 / 2 ← 超卖 10 件** |
| `available` 终值 | 10 → 0 | 变小但远没到 0 |
| 库存曾否为负 | **从未** | — |
| 审计捕获的写入次数 | **恰好 10 次，严格递减，0 次脏值** | — |
| 耗时 | 0.53s | 2.81s（20 个 UPDATE 争同一把行锁，只能排队） |
| 断言 | **12 / 12 全绿** | — |

**★★ 这里最重要的一条经验**：对照组超卖时 `total = available + locked + sold` **依然成立**
（`8 + 2 = 10`）。也就是说 **库存恒等式只能证明「账目不矛盾」，不能证明「卖出的没超过库存」**。
真正的判据是 **订单数 vs 库存扣减量**（`20 vs 2`）。做对账时，光跑恒等式会给你一个假的安全感。

**为什么用数据库触发器而不是轮询采样**：Python 每查一次库要起一个 `docker exec`（约 200ms），
而整场竞争只有 0.5 秒 —— 轮询只能采到 2 个点，等于没采。触发器是**每一次写入都留痕**，这才是硬证据。

> 同一装置还暴露了一个**与超卖性质不同**的问题：**一车多单** —— 同一份购物车被并发提交时，
> 1 件商品开出了 **7 张订单**（并发请求都读到了同一份快照）。超卖是库存侧原子性问题，
> 这个是**订单侧缺幂等键**（`requestId` 唯一索引 / Redis 去重），已列入 V1.1。

复现：

```bash
# 前置：应用在 8080 运行，数据库在 5434
docker exec -i mallx-postgres psql -U mallx -d mallx < backend/loadtest/day12-loadtest-setup.sql
python backend/loadtest/day12-concurrent-order.py
python backend/loadtest/day12-one-cart-multi-order.py
docker exec -i mallx-postgres psql -U mallx -d mallx < backend/loadtest/day12-loadtest-cleanup.sql
```

### 1.2 并发支付：20 线程支付同一张订单

装置：`day13-payment-concurrent.py`（订单号由脚本内确定，`payments` 行数与金额直接从库读）

| 判据 | 主组（CAS：`WHERE status = 'PENDING_PAYMENT'`） | 对照组（先查后改） |
|---|---|---|
| 成功 / 拒绝 | **1 / 19**，19 个全部是 `code=400 订单状态不允许支付` | 全部成功 |
| `payments` 新增 | **恰好 1 行** | **+12 行，`sum = 233,964.00`** |
| 该订单应收 | 19,497.00 | 19,497.00 |
| 结果 | 恰好成交一次 | **同一张单收了 12 笔钱**（19,497 → 233,964） |
| 库存 | `locked` 精确 −N、`sold` 精确 +N | 被扣 12 次 |

**★ 客户端本身也是变量，必须排除。** 第一版对照组只跑出 **7 笔** 重复支付，
当时看着像「服务端其实挡住了一部分」——查下去发现**问题在客户端**：
连接未预热，20 个请求实际到达间隔过大，没几对落在竞态窗口内。

| 版本 | 发请求方式 | 20 个请求实际到达间隔 | 重复支付 |
|---|---|---|---|
| 第一版 | 每请求新建连接 | 间隔过大 | 7 笔 |
| 改进版 | **预热连接**（先 `GET /api/hello` 建连，屏障放行后复用同一条 socket） | ~35ms | **12 笔** |

> ★ 做并发测试前先确认**你的客户端真的是并发的**，否则测出来的是「客户端有多串行」。
> 破坏力 ∝ 落在竞态窗口内的线程数，不是「只要并发就必然 20/20」。

复现：

```bash
python backend/loadtest/day13-payment-concurrent.py     # 自带造单与还原
```

### 1.3 这两次压测给出的通用结论

1. **扣库存 / 状态推进一律「条件 UPDATE（CAS）」，影响行数即答案** ——
   `0 行` = 条件不满足，绝不先查后改（TOCTOU）。
2. **`SET x = x - n` 而不是 `SET x = 具体值`** —— 减法由数据库做；
   Java 算的前提是「我知道当前值」，这个前提在并发下不成立。
3. **用 `updateById` 全量更新会覆盖别人刚改的字段（丢失更新）**，比超卖更隐蔽。
4. **恒等式全绿 ≠ 数据正确**（两处对照组都验证了这一点）。

---

## 二、资金与库存一致性

| 脚本 | 验什么 | 断言 | 报告 |
|---|---|---|---|
| `day14-ledger-verify.py` | 库存三段式台账：每次变更的 `sum(chg)` 与 `available/locked/sold` 逐笔吻合 | **61 / 61** | `day14-ledger-verify-report.txt` |
| `day14-reconcile.py` | 全 SKU 对账：`first_before + sum(流水) == last_after`，逐 SKU 出 verdict | **27 / 27** | `day14-reconcile-report.txt` |
| `day14-timeout-verify.py` | 支付超时路径（超时关单 / 库存回补） | **22 / 22** | `day14-timeout-verify-report.txt` |
| `day14-e2e-walk.py` | 下单 → 支付 → 发货 → 确认收货 → 评价 全链路（两条状态机出口 + 台账） | **67 / 67** | `day14-e2e-walk-report.txt` |

判据的特点是**逐字节对账**：不满足于「金额看起来对」，而是把流水按 SKU 累加后与当前库存列比对。

复现：

```bash
python backend/loadtest/day14-ledger-verify.py
python backend/loadtest/day14-reconcile.py
```

---

## 三、M1 全链路回归（每次改动必跑）

`day17-m1-regression.py` 是项目的**主回归闸门**：它不自己写断言，而是
「① 拍全表计数基线 → ② 依次跑 5 个已验收脚本 → ③ 比对基线 + 校验报告新鲜度」。

| 段 | 脚本 | 覆盖 | 断言 |
|---|---|---|---|
| 链路 | `day14-e2e-walk.py` | 下单 → 支付（两条状态机出口 + 台账） | 67 |
| 链路 | `day15-ship-confirm.py` | 支付 → 发货 → 确认收货 | 56 |
| 链路 | `day16-review-e2e.py` | 确认收货 → 评价（含评分聚合） | 75 |
| 读侧 | `day17-a-order-list-verify.py` | 订单列表（分页不重不漏、VO 逐字段与 DB 一致） | 26 |
| 读侧 | `day17-b-order-detail-verify.py` | 订单详情（含 `discountAmount` 口径） | 21 |
| | | **合计** | **245** |

它同时把五件事一次问完（任何一项不成立都不算通过）：

| | 问题 | 判据 |
|---|---|---|
| a | 每条链路是否全绿 | 5 份报告 `passed == total` |
| a2 | 读侧是否仍与库一致 | 同上 |
| b | 报告是否**本次生成** | 报告 mtime 晚于本次 stamp（防「拿上周的报告冒充」） |
| b2 | 报告是否**收齐** | `[1c] COVERAGE`：实收报告数 == 名单条数 |
| c | 数据库是否回到基线 | 全表计数快照逐项相等 → `BASELINE RESTORED: YES` |
| d | 里程碑不变量是否全零 | 无残留订单 / 无负库存 / 无重复支付 |

> **★ 为什么「回基线」是硬判据**：脚本写错、清理漏跑、事务没回滚……现象都可能是
> 「断言全绿但库里多了三行」。只有把**全表计数**在跑前拍下来，跑后再比一次，
> 残留才无处藏身。反过来，任何**故意留下数据**的验收脚本都会让 M1 报 `BASELINE RESTORED: NO` ——
> 这是设计上的强制约束，不是噪音。

复现：

```bash
cd backend/loadtest
python day17-m1-regression.py --baseline
python day14-e2e-walk.py && python day15-ship-confirm.py && python day16-review-e2e.py
python day17-a-order-list-verify.py && python day17-b-order-detail-verify.py
python day17-m1-regression.py
```

---

## 四、各域验收矩阵

| 脚本 | 域 | 断言 |
|---|---|---|
| `day17-m1-regression.py` | **M1 全链路回归**（见 §三） | **245** |
| `day17-c-order-cancel-verify.py` | 管理端取消订单（回补同源、流水口径、权限矩阵） | 42 |
| `day17-d-inventory-list-verify.py` | 管理端库存列表（分页夹紧四态） | 40 |
| `day17-e-inventory-adjust-verify.py` | 管理端库存调整 | 37 |
| `day17-f-inventory-log-verify.py` | 库存流水（id 降序、可选过滤与归一化） | 70 |
| `day17-fixture-apply.py` | 反向对照夹具（`op_order` / `op_product`，幂等 + 判别力） | 12 |
| `day18-b-admin-product-read-verify.py` | 管理端商品读（含下架口径，与 C 端成对照） | 51 |
| `day18-c-admin-product-write-verify.py` | 管理端商品写 + 数据迁移 | 42 |
| `day18-d-admin-category-read-verify.py` | 管理端分类读 | 16 |
| `day18-e-admin-category-write-verify.py` | 管理端分类写（两级约束、删除三重校验含「已软删商品」） | 40 |
| `day19-search-verify.py` | 搜索：全文 / `pg_trgm` / JSONB / 中文边界 / 索引 | 58 |
| `day20-coupon-verify.py` | 优惠券发放 / 领取 / 我的券（CAS + 唯一约束） | 82 |
| `day20-l1l2-verify.py` | 分页夹紧 + 下架商品可见性分流 | 33 |
| `day20-l5-brand-verify.py` | 品牌字典（C 端 / 管理端口径成对断言） | 24 |
| `day21-coupon-use-verify.py` | 下单抵扣 / 核销 / 取消退券 | 53 |
| `day22-admin-verify.py` | 用户管理 + 仪表盘口径 + 越权收口 | 67 |
| `day23-rbac-verify.py` | 管理员 / 角色 / 权限 / 分配 + 权限装载链路 | 91 |
| `day24-brand-crud-verify.py` | 品牌 CRUD + 权限矩阵反向对照 | 43 |
| `day25-api-inventory.py` | API 总览生成 + 源码↔运行时↔数据库三方核对 | 9 |
| `day25-readme-quickstart-check.py` | README「快速开始」每条命令实测 | 16 |
| `day25-compose-verify.py` | Docker Compose 全栈（含 initdb 链路完整性） | 12 |
| `day14-ledger-verify.py` / `day14-reconcile.py` / `day14-timeout-verify.py` | 台账 / 对账 / 超时（见 §二） | 61 / 27 / 22 |
| `day26-m1-fixture.py` | **M1 从零复现夹具**（幂等）：intruder + 地址 + 6 张 PAID 单 + 归零幽灵计数 | 31 |
| **合计（本表所列脚本自报断言数之和）** | | **1224** |

> ★ **口径必须写出来，否则这个数复算不出来**：「合计」是**本表所列**脚本自己报告的断言条数之和，
> 不是「1224 个互不相同的测试用例」，也**不是**全仓脚本的机械求和 ——
> 只有**打真实应用**（HTTP + `docker exec psql` 直查库）的验收脚本计入；
> `*-xml-check` / `*-perm-apply` / `*-skeleton-smoke` / `*-sec-probe` / `*-github-audit`
> 等**辅助脚本**格式各异、按次使用，**不计入**。
>
> ★★ **这个指标有一个已知盲区，所以两个数并列记**：1224 的用途是「观察回归覆盖面有没有缩水」，
> 但 `day25-sql-strict-check.py`（**16** 条，CI 必跑的门禁）**不在 1224 里** ——
> 它整份消失时，1224 **纹丝不动**。
>
> | 口径 | 条数 |
> |---|---|
> | **应用级验收**（打真实 HTTP + 直查库，本表所列） | **1224** |
> | **含 SQL / 工具类护栏**（+ `day25-sql-strict-check.py` 16 条 + `day27-explain-audit.py` 38 条 + `day28-search-rewrite-probe.py` 24 条） | **1302** |
>
> （实测：全仓 55 份 `*-report.txt` 中，当前仅 **9** 份以 `ASSERTIONS: n / m passed` 结尾、
> **6** 份用 `TOTAL:` / `FIXTURE:`，其余是逐次运行留下的一次性产物
> ⇒ 这个数**只能按本表维护，不能靠 grep 复算**。）
> 另外每个脚本都带**满额护栏**：报告里写死期望条数（如 `EXPECTED=43`），实得条数与之不符就判 FAIL ——
> 防止「断言没被创建」导致**假通过**。

---

## 五、搜索与索引

Day 19 把商品搜索全部放在 PostgreSQL（不引 ES），用了三件索引：

| 索引 | 承载的查询 |
|---|---|
| `idx_products_search`（tsvector + **GIN**） | `search_vector @@ plainto_tsquery(...)` 全文检索 |
| `idx_products_name_trgm`（`pg_trgm` + **GIN**） | `name % kw` 相似匹配 |
| `idx_products_skus_attributes`（**JSONB** + GIN） | `attributes @> '{"color":"黑色"}'` 属性筛选 |

### ★ 小表上「看不到索引」不是做错了

`EXPLAIN` 在只有 5 行的 `products` 上**一定选 `Seq Scan`** —— 全表扫描比「读索引再回表」便宜，
规划器是对的。所以直接在 5 行数据上跑 `EXPLAIN` 看不出 GIN，**这不是缺陷**。

想证明**索引本身可用**，要按下面两步（只做第一步不够）：

```sql
-- ① 只关 seqscan 还不够
BEGIN;
SET LOCAL enable_seqscan = off;
EXPLAIN SELECT id FROM products WHERE search_vector @@ plainto_tsquery('simple','iphone');
-- 这里可能是 Bitmap Heap Scan on products + Filter: is_deleted = 0
-- ⇒ ★ 因为 is_deleted = 0 自己有一条可用索引，规划器仍然不走 GIN
ROLLBACK;

-- ② 剥到【只剩该索引的谓词】才看得到
BEGIN;
SET LOCAL enable_seqscan = off;
EXPLAIN SELECT id FROM products WHERE search_vector @@ plainto_tsquery('simple','iphone');
-- ★ 去掉 is_deleted 谓词后：Bitmap Index Scan on idx_products_search
ROLLBACK;
```

> **诚实记录**：完整生产 SQL 在 5 行小表上，规划器选的仍然是 `Seq Scan`。
> **绝不为了「让 EXPLAIN 好看」往真实表里插几千行测试数据** —— Day 18 已经发生过一次
> 测试数据污染真实表的事故（误建商品 31 / 分类 36-37），代价远大于一张好看的执行计划。
>
> ★★ 但这句话有个危险的副作用：**它让「索引没被用上」永远无法被证伪** ——
> 5 行时是「正常」，30 万行时也能被同一句话糊过去。
> **正确做法是建临时库，而不是往真实表灌数**（Day 27 已这么做，见下）。

### ★★★ Day 27 实测：这 8 个索引，生产形状下到底有几个真在用（3 万行）

```bash
python backend/loadtest/day27-explain-audit.py
# 临时库 mallx_perf_probe：01→14 + 造数（products 3 万 / orders 3 万 / 流水 6 万）
# → VACUUM (ANALYZE) → 13 条查询 EXPLAIN (ANALYZE, BUFFERS) → DROP DATABASE
# 结果：38 / 38 passed，连跑三次一致。开发库零改动。
```

| 索引 | 生产形状下是否被用上 |
|---|---|
| `idx_products_search`（GIN） | ❌ **用不上** —— `searchProducts` 的 `OR` 把它挡住了 |
| `idx_products_name_trgm` | ❌ 同上（**单列**查询才生效：`1.3ms` vs 全表扫 `68.5ms`） |
| `idx_products_category_id` | ⚠️ 仅**不带 LIMIT** 的查询生效（C 端列表是 `ORDER BY id DESC LIMIT 10`，走 PK 反向扫） |
| `idx_products_status` | ❌ **死索引**（`status=1` 命中 99%，从不被选中） |
| `idx_products_skus_attributes`（GIN） | ✅ 有效（★ 计划器会把 `EXISTS` 反写成从 SKU 侧驱动） |
| `orders.user_id` · `orders.status` · `order_items.order_id` · `inventory_logs.sku_id` · `reviews.product_id` | ✅ 全部有效 |

**★★ 最值钱的一条**：`searchProducts` 的 `WHERE` 是
`(search_vector @@ ... OR name ILIKE ... OR subtitle ILIKE ... OR description ILIKE ...)`，
后两支 ILIKE 的列**没有索引** ⇒ 拼不出 `BitmapOr` ⇒ 只能全表扫。
**同一条 SQL 去掉 OR 之后，GIN 立刻被用上 —— 1.3 ms vs 68.5 ms，差 50 倍。**

⇒ **索引是好的，挡住它的是查询写法。** 这也正是「要不要上 ES / 加中间件」这个问题
必须先看 `EXPLAIN` 的原因：**当前最贵的一条查询是纯 SQL 问题，不是缺组件。**
（3 万行上 `orders.status` 那条 —— 即每 60 秒自动跑一次的超时关单扫描 —— 走的是索引，1.1ms。）

**怎么修：三个候选改法已量化**（Day 28 预研，`day28-search-rewrite-probe.py` **24/24**）

| 变体 | 做法 | EN `iphone` | CN `笔记本` |
|---|---|---|---|
| V0 | 现状（OR 四支） | 31 行 / **23.74 ms** / `Seq Scan` | 92 行 / **4.62 ms** / `Seq Scan` |
| **V1 ★推荐** | 补 `subtitle` / `description` 的 trgm 索引，**SQL 不动** | 31 行 / **0.82 ms** | 92 行 / **0.84 ms** |
| V2 | OR 拆成 `UNION` | 31 行 / 1.48 ms | 92 行 / 1.82 ms |
| V3 | 只留全文（去掉兜底） | 31 行 / 0.37 ms | **0 行** ← 中文黑洞 |

⇒ **推荐 V1**：比 V2 快约 2 倍，且**零 SQL 改动**（V2 要重写查询并顺带改分页口径）；
V3 对中文归零，**不是可选项**。三个变体的结果集都与 V0 **完全相等**（31/31、92/92）。

> ★ 两个隐藏陷阱（都实测过）：
> **① `UNION ALL` 会返回 212 行，而正确值是 92** —— `name` 与 `description` 都含该词的商品被数两次，
> 所以「拆 OR」必须去重。
> **② 中文必须写成连续无空格的 CJK 串才测得准** —— 第一版造数写成 `' 笔记本'`（带空格）时，
> 它成了独立 token，全文**假命中**（V3 返回 90 行）。改成 `'笔记本高清屏'` 后 V3 归零，
> 这才暴露出「搜索黑洞」的真实成因：**不是中文不能全文检索，是粒度不匹配。**
>
> 方案与验收清单见 `docs/daily/Day-28-搜索索引修复方案.md`。

> ★ 另一条只在**使用层**才踩得到的坑：批量灌数后 GIN 的 `fastupdate` **待处理列表**未清时，
> GIN 扫 32 行要 `13.3ms / 298 次 buffer`，计划器因此**放弃索引**；
> `VACUUM (ANALYZE)` 之后同一条查询降到 `0.9ms / 19 次`，成本估算从 `1266` 掉到 `21.4`。
> ⇒ **审计脚本必须 `VACUUM (ANALYZE)`，只 `ANALYZE` 会得到会翻转的结论**
> （Day 27 前几轮就是这么被骗的，一度误判为「计划器临界区」）。

搜索口径另有两条已修缺陷（均有回归断言盯着）：
`description` 参与检索（修复前 `keyword=笔记本` 恒返回 0，属**搜索黑洞**）、
父分类 `categoryId` 能展开到子分类（且与商品列表口径**相等**）。

复现：

```bash
python backend/loadtest/day19-search-verify.py    # 搜索口径断言
python backend/loadtest/day27-explain-audit.py    # 索引是否真被用上
```

---

## 六、已知边界与限额

| 项 | 现状 | 说明 |
|---|---|---|
| 分页上限 | `size ≤ 100`，`size <= 0` 夹紧为默认值 | 夹紧写在 `new Page<>()` **之前**；四态（负 / 0 / 正常 / 超限）都有断言 |
| 小表执行计划 | 规划器选 `Seq Scan` | ★ Day 27 已用**临时库 + 3 万行**实测：`idx_products_search` 在真实 SQL 下**仍然用不上**（被 `OR` 挡住），不是「数据量上来就自然切到 GIN」，见 §五 |
| 订单侧幂等 | **缺** | 「一车多单」实测 1 件商品开出 7 张单；需 `requestId` 唯一索引或 Redis 去重（V1.1） |
| 缓存 / 异步 | **无** | V1.0 刻意不引 Redis / MQ，「用关系库把该做的事做完」是第一约束 |
| 连接池 / 限流 | 未做 | V1.2 性能优化 |
| 压测规模 | 20 线程量级 | 目的是**证明正确性**，不是压容量；未做吞吐 / 延迟分布测量 |

---

## 七、怎么自己复现全部结论

```bash
# 0) 环境：PostgreSQL 在 5434，应用在 8080（见 README「快速开始」）
# 1) 并发正确性
python backend/loadtest/day12-concurrent-order.py        # 20 线程抢 10 件（含对照组）
python backend/loadtest/day13-payment-concurrent.py      # 20 线程付同一单（含对照组）
# 2) 一致性
python backend/loadtest/day14-ledger-verify.py
python backend/loadtest/day14-reconcile.py
# 3) 主回归闸门（务必按顺序：先拍基线）
cd backend/loadtest
python day17-m1-regression.py --baseline
python day14-e2e-walk.py && python day15-ship-confirm.py && python day16-review-e2e.py
python day17-a-order-list-verify.py && python day17-b-order-detail-verify.py
python day17-m1-regression.py                            # → 245/245 + BASELINE RESTORED: YES
```

所有脚本都会把自己的结论写成同名 `*-report.txt`，便于与上面的数字逐项对照。
