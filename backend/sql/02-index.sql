-- ============================================================
-- MallX 数据库索引（Day 03）
-- 说明：需在 01-schema.sql 之后执行。可重复执行（幂等）。
-- 说明：部分字段因 UNIQUE 约束已由 PG 自动建立唯一索引
--       （users.username / phone / email、orders.order_no、
--        product_skus.sku_code、payments.payment_no 等），
--       此处不再重复创建。
-- ============================================================

-- ------------------------------------------------------------
-- 一、用户索引
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_user_addresses_user_id ON user_addresses(user_id);

-- 部分唯一索引：把「每个用户最多一条默认地址」这条业务规则下推到数据库。
--   ① WHERE 只对 is_default = true 的行生效 —— 普通地址（false）可以有任意多条；
--   ② user_addresses 没有其它 UNIQUE 约束，所以「两条默认」全靠代码纪律守住，
--      任何绕过 Service 的写入（脚本、批量导入、写错的 SQL）都会静默产生脏数据；
--   ③ 有了它，第二条默认直接撞 23505，脏数据根本落不了库；
--   ④ 与 Service 的「先清后置（同一事务）」不冲突：同一事务内先 UPDATE 清掉旧的，再置新的。
CREATE UNIQUE INDEX IF NOT EXISTS uk_user_addresses_default
    ON user_addresses(user_id) WHERE is_default = true;

-- ------------------------------------------------------------
-- 二、商品索引
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_products_category_id ON products(category_id);
CREATE INDEX IF NOT EXISTS idx_products_brand_id    ON products(brand_id);
CREATE INDEX IF NOT EXISTS idx_products_status      ON products(status);

-- ------------------------------------------------------------
-- 三、SKU / 商品图片索引
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_product_skus_product_id ON product_skus(product_id);
CREATE INDEX IF NOT EXISTS idx_product_images_product_id ON product_images(product_id);

-- ------------------------------------------------------------
-- 四、库存索引
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_inventory_logs_sku_id ON inventory_logs(sku_id);

-- ------------------------------------------------------------
-- 五、购物车索引
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_cart_items_user_id ON cart_items(user_id);
CREATE INDEX IF NOT EXISTS idx_cart_items_sku_id  ON cart_items(sku_id);

-- ------------------------------------------------------------
-- 六、订单索引
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_orders_user_id     ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_status      ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_created_at  ON orders(created_at);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_sku_id ON order_items(sku_id);

-- ------------------------------------------------------------
-- 七、支付 / 评价 / 售后索引
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_payments_order_id ON payments(order_id);
CREATE INDEX IF NOT EXISTS idx_reviews_product_id ON reviews(product_id);
CREATE INDEX IF NOT EXISTS idx_reviews_user_id    ON reviews(user_id);
CREATE INDEX IF NOT EXISTS idx_after_sales_order_id ON after_sales(order_id);
CREATE INDEX IF NOT EXISTS idx_after_sales_user_id  ON after_sales(user_id);

-- ------------------------------------------------------------
-- 八、营销索引
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_user_coupons_user_id   ON user_coupons(user_id);
CREATE INDEX IF NOT EXISTS idx_user_coupons_coupon_id ON user_coupons(coupon_id);
CREATE INDEX IF NOT EXISTS idx_coupons_status         ON coupons(status);

-- ------------------------------------------------------------
-- 九、RBAC 索引
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_admin_roles_role_id        ON admin_roles(role_id);
CREATE INDEX IF NOT EXISTS idx_role_permissions_permission_id ON role_permissions(permission_id);

-- ------------------------------------------------------------
-- 十、JSONB GIN 索引（SKU 动态属性查询）
--    支持：WHERE attributes @> '{"color":"黑色"}'
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_product_skus_attributes
    ON product_skus USING GIN (attributes);

-- ------------------------------------------------------------
-- 十一、商品全文搜索 GIN 索引
--    支持：WHERE search_vector @@ plainto_tsquery('simple','iphone')
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_products_search
    ON products USING GIN (search_vector);

-- ------------------------------------------------------------
-- 十二、商品名称 pg_trgm 模糊搜索索引（需 pg_trgm 扩展）
--    支持：WHERE name ILIKE '%iphone%'（加速 LIKE / ILIKE）
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_products_name_trgm
    ON products USING GIN (name gin_trgm_ops);
