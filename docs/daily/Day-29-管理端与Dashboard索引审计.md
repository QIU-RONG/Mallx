# Day 29 — 管理端 / Dashboard 聚合查询的索引审计

> 本日**没有改一行 Java、没有动一个 DDL、没有加一个索引**。做的还是同一件事：
> 把「这里应该慢吧」变成数字 —— 而且这次得到的**主要是否定结论**，那同样有价值。

---

## 一、一句话结论

**`payments` 上确实缺索引，但给它加索引几乎没用 —— 不建议加。**
而「索引没被用上」这件事，**有两种成因完全相反的版本**，见 §五。

---

## 二、为什么审这里

Day 27 审的是**商品侧** 13 条查询；管理端与 Dashboard **从没被审过**。
而 `DashboardMapper.xml` 的 5 条查询里，有 2 条直接打在 `payments` 上：

```sql
-- sumPaidAmount
SELECT coalesce(sum(amount), 0) FROM payments WHERE status = 'SUCCESS'

-- selectDailyTrend 的 p CTE
SELECT to_char(paid_at, 'YYYY-MM-DD'), sum(amount) FROM payments
WHERE status = 'SUCCESS' AND paid_at >= CAST(? AS date) GROUP BY 1
```

★ 而 `02-index.sql` 里 `payments` **只有 `idx_payments_order_id`** ——
`status` 与 `paid_at` 上**一个索引都没有**。按 Day 27 的经验，这看起来像一条大鱼。

---

## 三、方法：对照实验 + 「不改数」判据

```
临时库 mallx_dash_probe
  → 灌 01→14
  → 造数：users 5000 / products 3 万 / orders 3 万（created_at 铺开 20 天）/ payments 3 万（SUCCESS 95%）
  → VACUUM (ANALYZE)
  → 【阶段 A】记录基线计划与耗时
  → 加候选索引 probe_payments_status / probe_payments_status_paid_at + VACUUM (ANALYZE)
  → 【阶段 B】重测
  → DROP DATABASE
```

两条判据（沿用 Day 28）：

1. **对照实验**：光说「全表扫」没用，要说「加上这个索引之后变成什么、快多少」；
2. ★ **加索引不能改数**：5 条查询的返回值必须在加索引前后**逐值相等** ——
   否则那不是优化，是把口径改坏了。（实测：5 条 `md5` 全等。）

结果：**20 / 20 passed**，`VERDICT: OK`。开发库零改动、生产 SQL 与索引一行不改。

---

## 四、结果

| ID | 查询 | A 基线 | B 加索引后 | 提升 | 计划变化 |
|---|---|---|---|---|---|
| D1 | `countUsers` | 1.78 ms | 2.14 ms | — | `Seq Scan on users`（★ 见 §六） |
| D2 | `countProducts`（`is_deleted=0`） | 8.98 ms | 6.57 ms | — | `idx_products_is_deleted` |
| D3 | `countOrders` | 8.67 ms | 6.36 ms | — | `idx_orders_status` |
| **D4** | `sumPaidAmount`（`status='SUCCESS'`） | 10.66 ms | 11.10 ms | **0.96x** | ★ **仍 `Seq Scan on payments`** |
| **D5** | `selectDailyTrend` | 32.49 ms | 24.85 ms | **1.3x** | ✅ 用上 `probe_payments_status_paid_at` |

### 4.1 两个候选索引的命运完全不同

| 候选索引 | 是否被用上 | 值不值 |
|---|---|---|
| `payments(status)` 单列 | ❌ **完全没被用上** | **不值** —— `status='SUCCESS'` 命中 **95%** 的行，索引无胜算 |
| `payments(status, paid_at)` 复合 | ✅ 被用上 | **边缘** —— 只快 **1.3x**（32.49 → 24.85 ms），代价是每次支付写入多维护一个索引 |

★ **D4 是我的假设被实测否掉的地方。** 我原本断言「加完索引就该用上」，实测是：
加完之后计划器**照样全表扫**，耗时**一点没变**（10.66 → 11.10 ms，落在噪声里）。
**那是计划器对，不是索引没建好** —— 低选择性列上走索引只会更慢。
⇒ 所以我把这条断言从「必须用上」改成了**反向对照「仍然不该被用上」**，
它现在是**一条会失败的正确断言**（如果哪天它开始用这个索引，说明选择性假设变了）。

---

## 五、★★ 本日最值钱的一条：「索引没被用上」有两种成因，修法相反

Day 27 与 Day 29 都发现「索引没被用上」，但**根因与结论完全相反**：

| | Day 27 · `idx_products_search` | Day 29 · `payments(status)` |
|---|---|---|
| 现象 | 全表扫 23.74 ms | 全表扫 10.66 ms |
| **根因** | **查询写法**挡住了索引（`OR` 里的 ILIKE 列没索引 ⇒ 拼不出 `BitmapOr`） | **选择性不足**（`status='SUCCESS'` 命中 95%） |
| 加索引有用吗 | ✅ **有用**：补 trgm 索引后 **0.82 ms（29x）** | ❌ **没用**：加了照样全表扫，0.96x |
| 该怎么办 | **改索引或改 SQL** | **别加** —— 加了只是多一份写入成本 |

⇒ 判据：**看到「全表扫」不要直接下结论「缺索引」。**
先问一句：**是查询没给它机会，还是它本来就没胜算？**
前者改索引/改 SQL 收益巨大（29x），后者加索引纯属负担。

★ 这两天的对照，正是本项目一直在用的方法论的又一次现形：
**没有对照组与反例的「优化」，分不清是优化还是安慰剂。**

---

## 六、已知边界（不是缺陷）

**PG 里全表 `count(*)` 天生 O(n)，加任何索引都消不掉。** 实测（3 万行）：

| 查询 | 耗时 |
|---|---|
| `countUsers` | ~2 ms（5000 行） |
| `countProducts` | ~7–9 ms（3 万行） |
| `countOrders` | ~6–9 ms（3 万行） |

★ 这两个查询**故意不做断言**，只记录 —— 断言它只会得到一条假结论。
按线性外推：**300 万行时约 0.6–0.9 s**，届时需要计数表 / 物化视图（属 V1.2 议题）。
现在 3 万行，**不值得提前优化**。

---

## 七、过程中的一处自我纠错

第一版造数 `payments` 时子查询只取了 `id, rn`，却在 SELECT 里用 `o.created_at` ⇒
`ERROR: column o.created_at does not exist`（`rc=3`）。

★ 值得记的不是这个笔误，而是**它被立刻抓住了**：包 `psql` 的 helper 暴露了 `stderr`，
`[4] 规模核对` 紧接着报 `payments 行数 >= 30000 → actual=0`。
这正是项目 Day 14 定下的那条约定（**helper 必须暴露 stderr，否则 SQL 错误会伪装成「没数据」**）
在起作用 —— 否则我会拿着一张「payments 全表扫只要 0.07 ms」的假报告去下结论。

（第一版真的出现过这个假数字：payments 空表时 D4 = **0.07 ms**。）

---

## 八、结论与下一步

**本日不改任何东西。** 得到的是一条**否定结论**与一条**判据**：

- ❌ 不建议为 `payments` 加索引（单列无用、复合只快 1.3x 且要付写入成本）。
- ✅ 管理端 / Dashboard 目前**没有需要立刻处理的性能问题**：
  最慢的 `selectDailyTrend` 32 ms，且它的耗时**主要不在 payments 上**。
- ✅ 「全表 count 是 O(n)」记录为**已知边界**，含 300 万行的外推。

**下一步候选**（优先级自上而下）：

1. **实现 Day 28 的搜索修复**（唯一有量级收益的一条：29x）—— 方案已备，等你动手。
2. 把 `day27` / `day28` / `day29` 三个审计脚本**挂进 CI**（都已是幂等 + 零副作用的临时库脚本）。
3. 删掉死索引 `idx_products_status`（取证已备：全仓仅 `02-index.sql:29` 一处引用）。
4. V1.2 的剩余项：慢查询治理 / 索引复盘 —— **本日的证据表明现在还不需要**。

---

## 九、复现

```bash
cd backend/loadtest
python day29-dashboard-explain-audit.py     # 20/20
```
