-- ============================================================
-- Day 12 第 3 步：压测夹具清理
-- 目标：删掉全部压测痕迹，把库还原到「第 2 步验收后」的状态
--   保留：orders id=1,2（第 2 步的样本订单）+ 其 order_items
--   复原：sku3 = total 60 / available 58 / locked 2（第 2 步下单 2 件后的状态）
-- ============================================================

\echo '=== BEFORE CLEANUP ==='
SELECT 'orders_all'   AS k, count(*)::bigint AS v FROM orders
UNION ALL SELECT 'orders_lt',  count(*)::bigint FROM orders WHERE user_id BETWEEN 1001 AND 1020
UNION ALL SELECT 'orders_demo_extra', count(*)::bigint FROM orders WHERE user_id = 1 AND id > 2
UNION ALL SELECT 'users_lt',   count(*)::bigint FROM users WHERE id BETWEEN 1001 AND 1020
UNION ALL SELECT 'audit_rows', count(*)::bigint FROM lt_stock_audit
UNION ALL SELECT 'sku3_available', available_stock::bigint FROM inventories WHERE sku_id = 3;

-- ① 压测用户的订单（先子后主），再清购物车 / 地址 / 用户
DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE user_id BETWEEN 1001 AND 1020);
DELETE FROM orders      WHERE user_id BETWEEN 1001 AND 1020;
DELETE FROM cart_items  WHERE user_id BETWEEN 1001 AND 1020;
DELETE FROM user_addresses WHERE user_id BETWEEN 1001 AND 1020;
DELETE FROM users       WHERE id BETWEEN 1001 AND 1020;

-- ② demo 用户在第 3 步「一车多单」实验里重复开出的订单（样本订单 1、2 必须留下）
DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE user_id = 1 AND id > 2);
DELETE FROM orders      WHERE user_id = 1 AND id > 2;
DELETE FROM cart_items  WHERE user_id = 1;

-- ③ 卸掉审计触发器与表（临时观测装置，不属于业务 schema）
DROP TRIGGER IF EXISTS trg_lt_audit ON inventories;
DROP FUNCTION IF EXISTS lt_audit_stock();
DROP TABLE IF EXISTS lt_stock_audit;

-- ④ 复原库存：sku3 回到第 2 步验收后的值
UPDATE inventories
SET total_stock = 60, available_stock = 58, locked_stock = 2, sold_stock = 0
WHERE sku_id = 3;

-- ⑤ 显式 id 的临时数据删完后，把序列拉回真实最大值
SELECT setval(pg_get_serial_sequence('users', 'id'),          (SELECT COALESCE(MAX(id), 1) FROM users));
SELECT setval(pg_get_serial_sequence('user_addresses', 'id'), (SELECT COALESCE(MAX(id), 1) FROM user_addresses));

\echo '=== AFTER CLEANUP ==='
SELECT 'users'          AS k, count(*)::bigint AS v FROM users
UNION ALL SELECT 'addresses',      count(*)::bigint FROM user_addresses
UNION ALL SELECT 'orders',         count(*)::bigint FROM orders
UNION ALL SELECT 'order_items',    count(*)::bigint FROM order_items
UNION ALL SELECT 'cart_items',     count(*)::bigint FROM cart_items
UNION ALL SELECT 'audit_table_exists', (to_regclass('lt_stock_audit') IS NOT NULL)::int::bigint
UNION ALL SELECT 'audit_trigger_exists', (to_regclass('inventories') IS NOT NULL
        AND EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_lt_audit'))::int::bigint
UNION ALL SELECT 'sku3_total',     total_stock::bigint     FROM inventories WHERE sku_id = 3
UNION ALL SELECT 'sku3_available', available_stock::bigint FROM inventories WHERE sku_id = 3
UNION ALL SELECT 'sku3_locked',    locked_stock::bigint    FROM inventories WHERE sku_id = 3
UNION ALL SELECT 'sku3_sold',      sold_stock::bigint      FROM inventories WHERE sku_id = 3;

\echo '=== identity check (all rows must be true) ==='
SELECT sku_id, total_stock, available_stock, locked_stock, sold_stock,
       (total_stock = available_stock + locked_stock + sold_stock) AS identity_ok
FROM inventories ORDER BY sku_id;

\echo '=== kept sample orders ==='
SELECT id, order_no, user_id, status, total_amount FROM orders ORDER BY id;
