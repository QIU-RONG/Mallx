-- ============================================================
-- 15. Day 28 搜索修复：补齐搜索兜底列上的 trgm 索引
-- ============================================================
-- 背景：docs/daily/Day-27-性能基线-EXPLAIN复盘.md —— searchProducts 的 OR 兜底
--       （ILIKE name / subtitle / description 三支）挡住了 GIN，
--       `idx_products_search` 在真实 SQL 下用不上（1.3 ms vs 68.5 ms 的那一条）。
-- 方案：docs/daily/Day-28-搜索索引修复方案.md —— V1 预研 24/24：
--       **只补索引、SQL 一字不改**（V1 比 V2 拆 UNION 快约 2 倍、零回归风险；
--       结果集与 V0 逐行相等：EN 31/31、CN 92/92）。
-- 机制：ILIKE '%kw%' 走 gin_trgm_ops 的 BitmapOr —— OR 的每一支各有索引可走，
--       计划器才能拼出 BitmapOr；此前只有 name 一列有 trgm（Day 03 的
--       idx_products_name_trgm），subtitle / description 是裸列。
-- 注意：
--   * 幂等：IF NOT EXISTS + 可重复执行，与其它补丁同一风格。
--   * 本项目唯一一类不需要 role_permissions 的补丁 —— 不引入新权限码。
--   * ★ 不改 02-index.sql（已上线库不会重跑它；新变更必须走新编号补丁）。
--   * ★ 不改 ProductMapper.xml（V1 的全部卖点就是 SQL 零改动）。
--   * ⚠️ 唯一代价：products 每次写入多维护 2 个 GIN 索引（Day 35 已证单个
--     二线索引写入成本 ≤ 噪声，本项目写少读多，可接受）。
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- 01-schema.sql 已建，此处幂等重申

CREATE INDEX IF NOT EXISTS idx_products_subtitle_trgm
    ON products USING GIN (subtitle gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_products_description_trgm
    ON products USING GIN (description gin_trgm_ops);

-- ★ ANALYZE 不能省（Day 27 的教训）：索引「建好了」与「计划器开始用它」
--   之间隔着统计信息；不做的话要等 autovacuum。
ANALYZE products;
