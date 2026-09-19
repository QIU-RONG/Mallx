-- ============================================================================
-- Day 14 · 实验后复原：按【业务守恒】把库存一次性归位
-- ----------------------------------------------------------------------------
-- 依据（与 day14-recalibrate.sql 同一套口径，但这里是【无条件】归位）：
--     locked 应 == SUM(PENDING_PAYMENT 订单的 order_items.quantity)
--     sold   应 == SUM(PAID            订单的 order_items.quantity)
--     available = total - locked - sold
--
-- ★ 为什么不能复用 day14-recalibrate.sql：
--   校准脚本只处理 drift > 0（多出的货退回可售），且它的第二段是
--   `WHERE locked_stock > 0` —— 而对照组把 locked 打成了【负数】(-19)，
--   那一段根本不会命中。对照组需要的是「无条件归位」。
--
-- ★ 前提：订单状态是账本上唯一可信的真相（locked/sold 都由订单推导）。
--   如果订单自身也被写坏了，这个脚本会跟着错 —— 所以跑完必须验 drift = 0。
-- ============================================================================

\pset border 2

\echo '=== BEFORE restore ==='
SELECT sku_id, total_stock, available_stock, locked_stock, sold_stock,
       (available_stock + locked_stock + sold_stock = total_stock) AS identity_ok
FROM inventories ORDER BY sku_id;

UPDATE inventories i
SET available_stock = i.total_stock
        - COALESCE((SELECT sum(oi.quantity) FROM order_items oi
                    JOIN orders o ON o.id = oi.order_id
                    WHERE oi.sku_id = i.sku_id AND o.status = 'PENDING_PAYMENT'), 0)
        - COALESCE((SELECT sum(oi.quantity) FROM order_items oi
                    JOIN orders o ON o.id = oi.order_id
                    WHERE oi.sku_id = i.sku_id AND o.status = 'PAID'), 0),
    locked_stock    = COALESCE((SELECT sum(oi.quantity) FROM order_items oi
                                JOIN orders o ON o.id = oi.order_id
                                WHERE oi.sku_id = i.sku_id AND o.status = 'PENDING_PAYMENT'), 0),
    sold_stock      = COALESCE((SELECT sum(oi.quantity) FROM order_items oi
                                JOIN orders o ON o.id = oi.order_id
                                WHERE oi.sku_id = i.sku_id AND o.status = 'PAID'), 0),
    updated_at      = CURRENT_TIMESTAMP;

\echo '=== AFTER restore ==='
SELECT sku_id, total_stock, available_stock, locked_stock, sold_stock,
       (available_stock + locked_stock + sold_stock = total_stock) AS identity_ok
FROM inventories ORDER BY sku_id;

\echo '=== drift (must be 0 rows) ==='
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
