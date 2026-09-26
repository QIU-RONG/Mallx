# Day 28 · 搜索修复落地 —— subtitle/description trgm 索引进补丁链

> 前情：Day 27 预研（`day28-search-rewrite-probe.py`，已冻结）证明生产搜索 SQL
> `name ILIKE OR subtitle ILIKE OR description ILIKE` 里，**只有 name 有 trgm 索引**，
> 另两列是 Seq Scan 黑洞；V1 方案（只补索引、SQL 一字不改）预期 **~29x**。
> 本日把 V1 从「方案稿」变成「补丁链 + 审计 + CI」。

## 一、落了什么

### 1. `backend/sql/15-search-trgm-indexes.sql`（新，幂等）

```sql
CREATE INDEX IF NOT EXISTS idx_products_subtitle_trgm
    ON products USING gin (subtitle gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_products_description_trgm
    ON products USING gin (description gin_trgm_ops);
ANALYZE products;
```

- 依赖 `pg_trgm` 扩展——`02-index.sql` 建 `idx_products_name_trgm` 时已 `CREATE EXTENSION IF NOT EXISTS`，此处不重复。
- **SQL 业务查询一字未改**（Day 27 结论：OR 兜底不该为了索引而重构，三列全有 trgm 后 `BitmapOr` 自然拼起来）。
- 已应用进开发库（`APPLY15=0`），initdb 挂载目录同源 ⇒ CI/全新库自动生效。

### 2. `day27-explain-audit.py` —— 期望翻转（4 处）

| 位置 | 改前 | 改后 |
|---|---|---|
| FILES | 01→14 | **01→15**（临时库必须灌进新补丁） |
| Q5 期望 | `NOT_INDEX:idx_products_search`（OR 挡住 GIN） | Q5 计划**必须含 4 个索引**（search + 3 trgm，BitmapOr） |
| Q6 期望 | `NOT_INDEX:idx_products_name_trgm` | Q6 同上（OR 不再挡路） |
| 核心结论断言 | 「生产搜索用不上索引」 | 「四个索引齐上」+ Q5 耗时对照 |

结果：**38/38**，Q5 实测 **1.468 ms**（修复前同形状 68.5 ms 量级）。

### 3. `day25-sql-strict-check.py` —— 补丁链 14→15

`FILES` 追加 15 号、`EXPECTED_FILES` 15、措辞同步；断言条数不变（无逐文件循环），**16/16**。

### 4. `day35-index-write-cost-probe.py` —— 口径同步（2 处）

FILES 01→15；products 组的候选 DROP 名单补进 2 个新 trgm。
重跑 **19/19**，对照组「全删写入提速」**32.3% → 44.0%**——GIN 写入成本可见变大，符合预期。

### 5. `day28-search-index-verify.py`（新，15/15）—— 落地验收

三段证据：
- **[计划]** 生产原形（**含 `LIMIT 10`**）四索引齐上（V0 对照：只有 name trgm）；
- **[等价性]** 补索引不改变结果：三关键词全量比对 91/91 + 62/62、top-10 完全一致；
- **[护栏]** 15 号补丁在 FILES、trgm 扩展在位、`ANALYZE` 后统计信息新鲜。

### 6. 回归 + CI

- 开发库应用 15 号后：夹具 31/31 → M1 五链 **245/245** → day19 搜索验收全绿。
- `ci.yml` Perf audits 追加 `day28-search-index-verify.py`，注释同步（01→15 特例标注）；pyyaml 预校验 OK。
- README 补丁链/脚本表/性能结论三处同步。

## 二、方法论教训（本日最有价值的一条）

验收脚本第一版把 day27 的查询**去掉了 `LIMIT 10`** 想测「全量等价」，
结果 V1 计划走了 Seq Scan——**不是修复无效**：没有 LIMIT 时随机堆回表代价估算压过索引收益，
计划器**合法地**选了 Seq Scan。生产形状本来就有 `LIMIT 10`（top-N 让 BitmapOr 显著便宜）。

⇒ **「样本要落在判据的取值域」**：断言「索引被用上」就必须用生产的查询形状，
改形状得到的「没走索引」是假信号。修正：计划断言用原形（LIMIT 10），等价性另用无 LIMIT 全量比对——两条都测，互不冒充。

## 三、附带修复

- `explain` 类取计划的函数补了 rc!=0 抛错（原来错误静默成空集合，会假绿）。

## 四、遗留

- `16-drop-dead-indexes.sql`（7 个死/冗余索引，Day 30/31/33/34 证据）待落——Day 35 探针已证明
  单索引写入成本小到测不出，**删除理由是「零读收益的纯负担」而非「省写入成本」**。
