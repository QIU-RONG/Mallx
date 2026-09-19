-- ============================================================
-- Day 12 第 3 步：并发压测夹具（纯 ASCII，避免 PS 5.1 GBK 读坏）
-- 模型：20 个【独立用户】并发下单，共同抢 sku_id=3 的 10 件库存
--   users 1001~1020  →  username = 'lt' + id
--   地址 id = 1000 + user_id  →  user 1001 的地址 = 2001（固定映射，脚本直接算）
-- 幂等：可反复执行，每次都回到同一基线
-- ============================================================

\echo '=== BEFORE ==='
SELECT 'orders_total' AS k, count(*)::bigint AS v FROM orders
UNION ALL SELECT 'sku3_available', available_stock::bigint FROM inventories WHERE sku_id = 3
UNION ALL SELECT 'users_lt', count(*)::bigint FROM users WHERE id BETWEEN 1001 AND 1020;

-- ① 20 个压测用户（password 用 {noop} 前缀 → DelegatingPasswordEncoder 直接放行）
INSERT INTO users (id, username, password, nickname, status)
SELECT v.id, 'lt' || v.id, '{noop}loadtest123', 'LT' || v.id, 1
FROM generate_series(1001, 1020) AS v(id)
WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.id = v.id);

-- ② 每人一条地址，id 固定为 1000 + user_id（NOT EXISTS 保证幂等）
INSERT INTO user_addresses (id, user_id, receiver_name, receiver_phone,
                            province, city, district, detail_address, is_default)
SELECT 1000 + u.id, u.id, 'LT', '13800138000',
       'Guangdong', 'Shenzhen', 'Nanshan', 'LT Street 1', TRUE
FROM users u
WHERE u.id BETWEEN 1001 AND 1020
  AND NOT EXISTS (SELECT 1 FROM user_addresses a WHERE a.id = 1000 + u.id);

-- ③ 显式 id 插入后必须校准序列，否则下一次自增插入撞主键
SELECT setval(pg_get_serial_sequence('users', 'id'),          (SELECT COALESCE(MAX(id), 1) FROM users));
SELECT setval(pg_get_serial_sequence('user_addresses', 'id'), (SELECT COALESCE(MAX(id), 1) FROM user_addresses));

-- ④ 库存靶子：sku_id = 3 设成总量 10、可售 10
--    ★ 这一步在触发器创建【之前】执行，所以不会污染审计日志
UPDATE inventories
SET total_stock = 10, available_stock = 10, locked_stock = 0, sold_stock = 0
WHERE sku_id = 3;

-- ⑤ ★ 库存审计：把每一次 UPDATE 之后的库存快照逐条记下来。
--    这是「并发过程中库存从未为负」的【硬证据】——不是定时采样猜的，
--    而是每一次写入都留痕，压测后能数出「恰好 10 次扣减、available 单调降到 0」。
CREATE TABLE IF NOT EXISTS lt_stock_audit (
    id        BIGSERIAL PRIMARY KEY,
    ts        TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    sku_id    BIGINT,
    available INT,
    locked    INT,
    sold      INT
);

CREATE OR REPLACE FUNCTION lt_audit_stock() RETURNS trigger AS $$
BEGIN
    INSERT INTO lt_stock_audit(sku_id, available, locked, sold)
    VALUES (NEW.sku_id, NEW.available_stock, NEW.locked_stock, NEW.sold_stock);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_lt_audit ON inventories;
CREATE TRIGGER trg_lt_audit
    AFTER UPDATE ON inventories
    FOR EACH ROW
    WHEN (OLD.sku_id = 3)
EXECUTE FUNCTION lt_audit_stock();

TRUNCATE lt_stock_audit;

-- ⑥ 清掉压测用户的历史订单与购物车（FK: order_items.order_id -> orders.id，先删子表）
DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE user_id BETWEEN 1001 AND 1020);
DELETE FROM orders      WHERE user_id BETWEEN 1001 AND 1020;
DELETE FROM cart_items  WHERE user_id BETWEEN 1001 AND 1020;

\echo '=== AFTER ==='
SELECT 'users_lt'       AS k, count(*)::bigint  AS v FROM users WHERE id BETWEEN 1001 AND 1020
UNION ALL SELECT 'addr_lt',        count(*)::bigint   FROM user_addresses WHERE user_id BETWEEN 1001 AND 1020
UNION ALL SELECT 'addr_min_id',    MIN(id)::bigint    FROM user_addresses WHERE user_id BETWEEN 1001 AND 1020
UNION ALL SELECT 'orders_total',   count(*)::bigint   FROM orders
UNION ALL SELECT 'orders_lt',      count(*)::bigint   FROM orders WHERE user_id BETWEEN 1001 AND 1020
UNION ALL SELECT 'cart_lt',        count(*)::bigint   FROM cart_items WHERE user_id BETWEEN 1001 AND 1020
UNION ALL SELECT 'audit_rows',     count(*)::bigint   FROM lt_stock_audit
UNION ALL SELECT 'sku3_total',     total_stock::bigint     FROM inventories WHERE sku_id = 3
UNION ALL SELECT 'sku3_available', available_stock::bigint FROM inventories WHERE sku_id = 3
UNION ALL SELECT 'sku3_locked',    locked_stock::bigint    FROM inventories WHERE sku_id = 3
UNION ALL SELECT 'sku3_sold',      sold_stock::bigint      FROM inventories WHERE sku_id = 3;
