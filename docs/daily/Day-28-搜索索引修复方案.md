# Day 28 — 让全文检索真正走上索引（方案 + 预研实测）

> **本文是方案稿，不是交付记录。** 本日**没有改生产代码、没有加索引、没有改 SQL** ——
> 按项目约定，实现由你来。本文做的是：把 Day 27 发现的问题（`idx_products_search`
> 在真实 SQL 下用不上）的**三个候选改法先量化**，再给出推荐与验收断言清单。
>
> 一句话结论：**只补两个 `pg_trgm` 索引、SQL 一个字不改，就是最快的方案。**

---

## 一、结论先行

脚本：`backend/loadtest/day28-search-rewrite-probe.py` → `day28-search-rewrite-probe-report.txt`
结果：**24 / 24 passed**（临时库 `mallx_search_probe`，3 万商品，跑完即删）

| 变体 | 做法 | EN `iphone` | CN `笔记本` |
|---|---|---|---|
| **V0** | 现状（OR 四支） | 31 行 / **23.74 ms** / `Seq Scan` | 92 行 / **4.62 ms** / `Seq Scan` |
| **V1 ★推荐** | 补 trgm 索引，**SQL 不动** | 31 行 / **0.82 ms** | 92 行 / **0.84 ms** |
| V2 | OR 拆成 `UNION` | 31 行 / 1.48 ms | 92 行 / 1.82 ms |
| V3 | 只留全文（去掉兜底） | 31 行 / 0.37 ms | **0 行** ← 搜索黑洞 |

- **V1 比 V2 快约 2 倍**，而且**零 SQL 改动**（V2 要重写查询、还要顺带改分页口径）。
- **V3 不可选**：中文返回 0 行，见 §二。
- ★ **结果集等价性成立**：V1 / V2 的行数与 V0 **完全相等**（31/31、92/92）。
  —— 这是本预研最重要的一条判据：**快 10 倍但少返回 20 行的改法不是优化，是缺陷。**

---

## 二、★ V3 为什么不可选 —— 以及我在这里踩的一个坑

「中文走全文恒返回 0」这句话**对，但机制不是我以为的那个**。

**第一版造数把中文写成 `' 笔记本'`（前面带一个空格）** ⇒ 它成了一个**独立的 token**
⇒ 全文**居然命中了**（V3 对中文返回 **90 行**，与预期完全相反）。

改成**连续无空格**的 CJK 串（`'笔记本高清屏'`）之后，全文返回 **0 行** —— 这才是真实中文的形态：
`to_tsvector('simple', ...)` 不切中文，**整段中文是一个 token**，查询 token 是 `笔记本`，
两者不相等 ⇒ 匹配不上。

⇒ 这同时解释了两件事：
1. Day 20 的 L3「搜索黑洞」的**真实成因**（不是「中文不能全文检索」，而是**粒度不匹配**）；
2. 为什么 ILIKE 兜底是**功能**而不是优化 —— 去掉它，中文搜索直接归零。

★ 判据（本脚本第 **4** 次踩）：**样本必须落在判据的取值域里。**
用「带空格的中文」去验「中文全文检索」，测的是一个**不存在于现实**的输入。

---

## 三、V2 的隐藏陷阱：必须 `UNION`，不能 `UNION ALL`

| 写法 | 中文结果行数 |
|---|---|
| `UNION`（去重） | **92**（= V0） |
| `UNION ALL` | **212** ❌ |

原因：`name` 与 `description` **都含**该词的商品会被数两次（造数里专门留了 `g % 1000 == 3` 这一组）。
⇒ 任何「把 OR 拆开」的改法，**去重不是可选项**。

---

## 四、要改哪些文件、每处写什么（实现用）

**新增 `backend/sql/15-search-trgm-indexes.sql`：**

```sql
-- Day 28：补齐搜索兜底列上的 trgm 索引，让 searchProducts 的 OR 能拼出 BitmapOr。
-- 背景见 docs/daily/Day-27-性能基线-EXPLAIN复盘.md（OR 挡住 GIN）与 Day-28 预研（V1 最快）。
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- 01-schema.sql 已建，此处幂等重申

CREATE INDEX IF NOT EXISTS idx_products_subtitle_trgm
    ON products USING GIN (subtitle gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_products_description_trgm
    ON products USING GIN (description gin_trgm_ops);

ANALYZE products;   -- ★ 让计划器立刻看到新索引；不做的话要等 autovacuum
```

| 要点 | 说明 |
|---|---|
| **幂等** | `IF NOT EXISTS` + 可重复执行，与其它 14 份补丁同一风格 |
| **不需要补权限** | ★ 本项目**唯一**一类不需要 `role_permissions` 的补丁 —— 它不引入新权限码（对照「按前缀批量授权」那条判据） |
| **不要改 `02-index.sql`** | 已上线的库**不会重跑**它；新变更必须走新编号补丁 |
| **不要改 `ProductMapper.xml`** | V1 的**全部卖点**就是 SQL 一个字不改 ⇒ 零回归风险 |
| ⚠️ **唯一代价** | 写入放大：`products` 每次写入要多维护 2 个 GIN 索引。本项目写少读多，可接受；但这是**真实成本**，要写进文档 |
| ⚠️ **`ANALYZE` 不能省** | Day 27 的教训：索引「建好了」与「计划器开始用它」之间隔着统计信息 |

**另外一件已有取证、但同样留给你决定的事**：删除死索引 `idx_products_status`。
取证：全仓（除 `.idea` 缓存）**只有 `02-index.sql:29` 一处引用**，无任何查询依赖它。

---

## 五、验收断言清单（实现后跑）

### 5.1 必须同步修改的既有断言（★ 先做这一步）

`day27-explain-audit.py` 里 **Q5 / Q6 的期望要翻转**：

| 查询 | 现在的期望 | 实现后应改为 |
|---|---|---|
| Q5 真实 `searchProducts`（含 OR） | `NOT_INDEX:idx_products_search` | `INDEX:idx_products_search` 或 `INDEX:idx_products_*_trgm` |
| Q6 中文兜底（OR 三列） | `NOT_INDEX:idx_products_name_trgm` | `INDEX:idx_products_name_trgm` |

⚠️ 改期望时**同步改 `EXPECTED_CHECKS`**（本项目已因漏改它现形过一次：脚本首跑就报「总数与 EXPECTED 不符」）。

### 5.2 新增 `day28-search-index-verify.py`（建议 12–16 条）

| # | 断言 |
|---|---|
| 1–3 | `pg_indexes` 里三张索引（`subtitle_trgm` / `description_trgm` / 原有 `name_trgm`）都存在 |
| 4 | `keyword=笔记本` 的行数与**修复前快照**相等（92） |
| 5 | `keyword=iphone` 的行数不变（31） |
| 6–7 | ★ **集合相等**（不只是行数相等）：两次查询的 `id` 集合逐一比对 |
| 8 | 空关键词不触发新分支（仍返回全部） |
| 9 | `categoryId` 与列表口径仍相等（L4 那条不能被打翻） |
| 10 | 分页 `size` 夹紧四态不受影响 |
| 11–12 | `day27` 的 Q5/Q6 按 5.1 翻转后全绿 |

### 5.3 回归（每次改动必跑）

- `day19-search-verify.py` **58 / 58**（★ L3 的 B10 / E 组是「ILIKE 范围」的产物，改索引不该动口径，但**必须复跑**）
- `day17-m1-regression.py` **245 / 245** + `BASELINE RESTORED: YES`
- `day25-sql-strict-check.py` **16 / 16**（新增 15 号补丁后，清单要从 14 份改成 **15 份**）
- ★ 把 `day28-search-index-verify.py` 挂进 `.github/workflows/ci.yml`

### 5.4 ★ 动手前的铁律

**先问：哪些断言是靠「这里还没有 X」才成立的？**
本项目已两次现形（Day 20 L3 的 `promotion` 证据、Day 24 T2 的「不存在路径 → 404」）。
本日新增的索引会**改变计划**，凡是断言了「走 Seq Scan」的地方都要回头扫一遍。

---

## 六、复现本预研

```bash
cd backend/loadtest
python day28-search-rewrite-probe.py     # 24/24
```

临时库 `mallx_search_probe`：灌 01→14 + 造数（3 万商品，含中英关键词的三种落点）→
`VACUUM (ANALYZE)` → 阶段 A 测 V0/V3 → **补索引 + `VACUUM (ANALYZE)`** → 阶段 B 测 V1/V2 → 删库。
**开发库零改动。**

> ★ 顺序不是随意的：V0/V3 必须在**补索引之前**测，否则 V0 会白蹭 V1 的索引，对照就废了。

---

## 七、本日边界

- **未改**生产代码 / SQL / 索引（实现留给你）。
- **未决定**是否删除 `idx_products_status`（取证已备）。
- **未涉及** Redis / RabbitMQ —— 本次证据进一步支持「先修 SQL，再谈中间件」：
  最贵的那条查询是**查询写法**问题，加组件只会把它藏起来。
