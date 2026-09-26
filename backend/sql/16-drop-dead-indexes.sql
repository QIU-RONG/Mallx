-- ============================================================================
-- 16-drop-dead-indexes.sql —— 死/冗余索引清理（Day 36）
--
-- 删除 7 个「零读收益的纯维护负担」索引，证据链：
--   Day 30/31  products 侧 EXPLAIN 复盘（低选择性 / 从未被计划选中）
--   Day 33     券侧两种冗余
--   Day 34     购物车两种冗余（A 型没被用上 / B 型被复合唯一索引左前缀覆盖）
--   Day 35     写入成本探针（19/19）：单个二线索引的写入成本 ≤ 噪声
--              ⇒ 删除理由是【卫生】而非【性能】——留着不炸，删了干净。
--
-- ★ 刻意不动（有真实查询在用，见各 Day 日志）：
--   idx_after_sales_* / idx_role_permissions_permission_id / idx_admin_roles_role_id
--
-- 幂等：全部 DROP INDEX IF EXISTS，可重复执行。
-- ============================================================================

-- ---- A 型：从未被任何生产查询的计划选中（低选择性 / 无按该列查询的入口） ----

-- Day 30/31：status 取值域极小，planner 恒走全表或其它索引
DROP INDEX IF EXISTS idx_products_status;
-- Day 31：布尔列索引，选择性 ~1 bit，等价于没有
DROP INDEX IF EXISTS idx_product_skus_is_deleted;
-- Day 30/31：没有任何接口按 sku_id 反查明细行
DROP INDEX IF EXISTS idx_order_items_sku_id;
-- Day 33：coupons.status 取值域极小，恒不被选中
DROP INDEX IF EXISTS idx_coupons_status;
-- Day 34：购物车按 sku_id 查无入口（加购/改选/删除全走 user_id）
DROP INDEX IF EXISTS idx_cart_items_sku_id;

-- ---- B 型：被复合唯一索引的左前缀覆盖（留着 = 纯写入开销 + 优化器噪音） ----

-- Day 34：uk_cart_user_sku(user_id, sku_id) 的左前缀即可服务所有 user_id 查询
DROP INDEX IF EXISTS idx_cart_items_user_id;
-- Day 33：09 号补丁的 uk_user_coupons_user_coupon(user_id, coupon_id) 左前缀同上
DROP INDEX IF EXISTS idx_user_coupons_user_id;

-- ---- 自检：7 个都必须已经不存在（留一个 = initdb 没跑到这里，立刻炸） ----
DO $$
DECLARE
    n int;
BEGIN
    SELECT count(*) INTO n FROM pg_indexes
    WHERE indexname IN ('idx_products_status', 'idx_product_skus_is_deleted',
                        'idx_order_items_sku_id', 'idx_coupons_status',
                        'idx_cart_items_sku_id', 'idx_cart_items_user_id',
                        'idx_user_coupons_user_id');
    IF n <> 0 THEN
        RAISE EXCEPTION 'SELF-CHECK FAIL: % 个死索引仍然存在', n;
    END IF;
    RAISE NOTICE 'SELF-CHECK OK: 7 个死/冗余索引已清理';
END $$;
