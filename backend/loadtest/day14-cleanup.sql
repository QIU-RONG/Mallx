-- ============================================================================
-- Day 14 · 清理并发实验的靶子订单
-- ----------------------------------------------------------------------------
-- 保留：9006 / 9007 —— Day 14 第 1 步验收的正常产物（干净的 CANCELLED 样本）
-- 删除：9008 ~ 9014 —— 第 2 步并发实验的靶子（每跑一轮造一张）
--       其中 9012 / 9013 是【对照组】留下的，各带 10 行脏 payments
--
-- 删除顺序（外键：payments 与 order_items 都引用 orders）：
--   payments -> order_items -> orders
--
-- ★ 删完不影响库存：这些订单终态都是 CANCELLED（不计入业务守恒的任何一个方向），
--   而且它们的库存已经由 day14-restore.sql 归位。删完必须复验 drift = 0。
-- ============================================================================

\pset border 2

\echo '=== BEFORE cleanup: target orders + their payment rows ==='
SELECT o.id, o.status, o.paid_at IS NOT NULL AS has_paid,
       o.cancelled_at IS NOT NULL AS has_cancel,
       (SELECT count(*) FROM payments p WHERE p.order_id = o.id) AS pay_rows
FROM orders o WHERE o.id BETWEEN 9008 AND 9014 ORDER BY o.id;

\echo '=== BEFORE cleanup: sku4 ==='
SELECT sku_id, total_stock, available_stock, locked_stock, sold_stock FROM inventories WHERE sku_id = 4;

DELETE FROM payments    WHERE order_id BETWEEN 9008 AND 9014;
DELETE FROM order_items WHERE order_id BETWEEN 9008 AND 9014;
DELETE FROM orders      WHERE id       BETWEEN 9008 AND 9014;

\echo '=== AFTER cleanup: orders / payments ==='
SELECT status, count(*) AS cnt FROM orders GROUP BY status ORDER BY status;
SELECT count(*) AS payments_rows FROM payments;

\echo '=== AFTER cleanup: sku4 (must be unchanged) ==='
SELECT sku_id, total_stock, available_stock, locked_stock, sold_stock,
       (available_stock + locked_stock + sold_stock = total_stock) AS identity_ok
FROM inventories WHERE sku_id = 4;

\echo '=== AFTER cleanup: drift (must be 0 rows) ==='
SELECT i.sku_id,
       i.locked_stock - COALESCE(l.want, 0) AS drift_locked,
       i.sold_stock   - COALESCE(s.want, 0) AS drift_sold
FROM inventories i
LEFT JOIN (SELECT oi.sku_id, sum(oi.quantity) AS want FROM order_items oi
           JOIN orders o ON o.id = oi.order_id
           WHERE o.status = 'PENDING_PAYMENT' GROUP BY oi.sku_id) l ON l.sku_id = i.sku_id
LEFT JOIN (SELECT oi.sku_id, sum(oi.quantity) AS want FROM order_items oi
           JOIN orders o ON o.id = oi.order_id
           WHERE o.status = 'PAID' GROUP BY oi.sku_id) s ON s.sku_id = i.sku_id
WHERE i.locked_stock <> COALESCE(l.want, 0) OR i.sold_stock <> COALESCE(s.want, 0)
ORDER BY i.sku_id;

\echo '=== AFTER cleanup: all 7 inventories ==='
SELECT sku_id, total_stock, available_stock, locked_stock, sold_stock FROM inventories ORDER BY sku_id;
