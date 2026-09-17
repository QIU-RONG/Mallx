-- ============================================================
-- MallX 数据库初始化数据（Day 03）
-- 说明：需在 01-schema.sql、02-index.sql 之后执行。
--      所有插入均做存在性判断，可重复执行（幂等）。
-- ============================================================

-- ------------------------------------------------------------
-- 一、商品分类（多级树）
-- ------------------------------------------------------------
INSERT INTO categories (id, parent_id, name, sort_order)
SELECT v.id, v.parent_id, v.name, v.sort_order
FROM (VALUES
    (1, NULL, '手机通讯', 1),
    (2, NULL, '电脑办公', 2),
    (3, NULL, '家用电器', 3),
    (11, 1,   '智能手机', 1),
    (12, 1,   '手机配件', 2),
    (21, 2,   '笔记本电脑', 1),
    (31, 3,   '电视', 1)
) AS v(id, parent_id, name, sort_order)
WHERE NOT EXISTS (SELECT 1 FROM categories c WHERE c.id = v.id);

-- 修正分类树的父级指向（保持引用完整性）
UPDATE categories c
SET parent_id = 1
WHERE c.id IN (11, 12) AND c.parent_id IS NULL;
UPDATE categories SET parent_id = 2 WHERE id = 21 AND parent_id IS NULL;
UPDATE categories SET parent_id = 3 WHERE id = 31 AND parent_id IS NULL;

-- ------------------------------------------------------------
-- 二、品牌
-- ------------------------------------------------------------
INSERT INTO brands (id, name, logo, description)
SELECT v.id, v.name, v.logo, v.description
FROM (VALUES
    (1, 'Apple',    'https://oss.mallx.local/brand/apple.png',    '美国科技公司，iPhone/Mac 等'),
    (2, 'Huawei',   'https://oss.mallx.local/brand/huawei.png',   '中国通信与消费电子品牌'),
    (3, 'Xiaomi',   'https://oss.mallx.local/brand/xiaomi.png',   '小米科技，手机/智能家居'),
    (4, 'Samsung',  'https://oss.mallx.local/brand/samsung.png',  '韩国电子品牌'),
    (5, 'Lenovo',   'https://oss.mallx.local/brand/lenovo.png',   '联想，笔记本/台式机'),
    (6, 'DJI',      'https://oss.mallx.local/brand/dji.png',      '大疆，无人机'),
    (7, '无品牌',   NULL, NULL)
) AS v(id, name, logo, description)
WHERE NOT EXISTS (SELECT 1 FROM brands b WHERE b.id = v.id);

-- ------------------------------------------------------------
-- 三、示例 SPU（插入会自动触发 search_vector 更新）
-- ------------------------------------------------------------
INSERT INTO products (id, category_id, brand_id, name, subtitle, description, main_image, status)
SELECT v.id, v.category_id, v.brand_id, v.name, v.subtitle, v.description, v.main_image, 1
FROM (VALUES
    (1, 11, 1, 'Apple iPhone 17 Pro',   '钛金属边框 3nm A19 Pro 芯片', '全新一代旗舰手机，配备 4800 万像素三摄与 120Hz ProMotion 屏。', 'https://oss.mallx.local/p/iphone17pro.jpg'),
    (2, 11, 2, 'Huawei Mate 80 Pro',    '卫星通信 麒麟芯片 徕卡影像', '华为高端旗舰，支持北斗卫星消息，超感知影像系统。', 'https://oss.mallx.local/p/mate80.jpg'),
    (3, 11, 3, 'Xiaomi 15 Ultra',       '徕卡光学 一英寸大底', '小米影像旗舰，2 亿像素潜望长焦，澎湃 OS。', 'https://oss.mallx.local/p/mi15u.jpg'),
    (4, 21, 5, 'Lenovo ThinkPad X1 Carbon', '商务轻薄本 2.2K 屏', '14 英寸商务笔记本，航空级碳纤维，超长续航。', 'https://oss.mallx.local/p/x1carbon.jpg'),
    (5, 21, 1, 'Apple MacBook Air M3',  '8GB 统一内存 轻至 1.24kg', '搭载 M3 芯片的轻薄笔记本，无风扇设计，全天候续航。', 'https://oss.mallx.local/p/mba-m3.jpg')
) AS v(id, category_id, brand_id, name, subtitle, description, main_image)
WHERE NOT EXISTS (SELECT 1 FROM products p WHERE p.id = v.id);

-- ------------------------------------------------------------
-- 四、示例 SKU（JSONB 动态属性）
-- ------------------------------------------------------------
INSERT INTO product_skus (id, product_id, sku_code, name, price, original_price, attributes, status)
SELECT v.id, v.product_id, v.sku_code, v.name, v.price, v.original_price, v.attributes::jsonb, 1
FROM (VALUES
    (1, 1, 'IP17P-BLK-256', '黑色 256GB',  9999.00, 10999.00, '{"color":"黑色","storage":"256GB","ram":"8GB"}'),
    (2, 1, 'IP17P-BLK-512', '黑色 512GB',  11999.00, 12999.00, '{"color":"黑色","storage":"512GB","ram":"8GB"}'),
    (3, 1, 'IP17P-TIT-512', '原色钛金属 512GB', 12499.00, 13499.00, '{"color":"原色钛金属","storage":"512GB","ram":"8GB"}'),
    (4, 2, 'MATE80-BLK-512', '曜金黑 512GB', 6999.00, 7499.00, '{"color":"曜金黑","storage":"512GB","ram":"12GB"}'),
    (5, 3, 'MI15U-WHT-512', '白色 512GB', 6499.00, 6999.00, '{"color":"白色","storage":"512GB","ram":"16GB"}'),
    (6, 4, 'X1C-I7-16-512', 'i7 16GB 512GB', 12499.00, 13999.00, '{"cpu":"Core i7","ram":"16GB","storage":"512GB"}'),
    (7, 5, 'MBA-M3-8-256', '星光色 8GB 256GB', 8999.00, 9499.00, '{"chip":"M3","ram":"8GB","storage":"256GB"}')
) AS v(id, product_id, sku_code, name, price, original_price, attributes)
WHERE NOT EXISTS (SELECT 1 FROM product_skus s WHERE s.id = v.id);

-- ------------------------------------------------------------
-- 五、商品图片
-- ------------------------------------------------------------
INSERT INTO product_images (product_id, image_url, sort_order)
SELECT v.product_id, v.image_url, v.sort_order
FROM (VALUES
    (1, 'https://oss.mallx.local/p/iphone17pro-1.jpg', 0),
    (1, 'https://oss.mallx.local/p/iphone17pro-2.jpg', 1),
    (2, 'https://oss.mallx.local/p/mate80-1.jpg', 0),
    (3, 'https://oss.mallx.local/p/mi15u-1.jpg', 0)
) AS v(product_id, image_url, sort_order)
WHERE NOT EXISTS (
    SELECT 1 FROM product_images i
    WHERE i.product_id = v.product_id AND i.image_url = v.image_url
);

-- ------------------------------------------------------------
-- 六、库存（一 SKU 一条）
-- ------------------------------------------------------------
INSERT INTO inventories (sku_id, total_stock, available_stock, locked_stock, sold_stock)
SELECT v.sku_id, v.total_stock, v.available_stock, v.locked_stock, v.sold_stock
FROM (VALUES
    (1, 100, 96, 2, 2),
    (2,  80, 78, 0, 2),
    (3,  60, 60, 0, 0),
    (4, 150, 148, 1, 1),
    (5, 120, 120, 0, 0),
    (6,  40, 39, 1, 0),
    (7,  90, 90, 0, 0)
) AS v(sku_id, total_stock, available_stock, locked_stock, sold_stock)
WHERE NOT EXISTS (SELECT 1 FROM inventories i WHERE i.sku_id = v.sku_id);

-- ------------------------------------------------------------
-- 七、演示用户
-- ------------------------------------------------------------
INSERT INTO users (id, username, password, nickname, phone, email, status)
SELECT v.id, v.username, v.password, v.nickname, v.phone, v.email, 1
FROM (VALUES
    -- password 明文仅为演示占位，实际项目用 BCrypt 加密（后续 Day 实现认证时处理）
    (1, 'demo',  '{noop}demo123',  '演示用户', '13800000001', 'demo@mallx.local')
) AS v(id, username, password, nickname, phone, email)
WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.id = v.id);

-- ------------------------------------------------------------
-- 八、RBAC 初始化：角色 / 权限 / 超级管理员
-- ------------------------------------------------------------
INSERT INTO roles (id, name, code, description)
SELECT v.id, v.name, v.code, v.description
FROM (VALUES
    (1, '超级管理员', 'SUPER_ADMIN', '拥有全部权限'),
    (2, '商品管理员', 'PRODUCT_ADMIN', '管理商品/分类/库存'),
    (3, '订单管理员', 'ORDER_ADMIN',   '处理订单/发货/售后')
) AS v(id, name, code, description)
WHERE NOT EXISTS (SELECT 1 FROM roles r WHERE r.id = v.id);

INSERT INTO permissions (id, name, code, type, path, method)
SELECT v.id, v.name, v.code, v.type, v.path, v.method
FROM (VALUES
    (1,  '商品列表',   'product:list',   'API', '/api/products',    'GET'),
    (2,  '商品详情',   'product:detail', 'API', '/api/products/*',  'GET'),
    (3,  '新建商品',   'product:create', 'API', '/api/products',    'POST'),
    (4,  '编辑商品',   'product:update', 'API', '/api/products/*',  'PUT'),
    (5,  '删除商品',   'product:delete', 'API', '/api/products/*',  'DELETE'),
    (6,  '订单列表',   'order:list',     'API', '/api/orders',      'GET'),
    (7,  '订单发货',   'order:ship',     'API', '/api/orders/*/ship','POST'),
    (8,  '用户列表',   'user:list',      'API', '/api/users',       'GET')
) AS v(id, name, code, type, path, method)
WHERE NOT EXISTS (SELECT 1 FROM permissions p WHERE p.id = v.id);

-- 超级管理员
INSERT INTO admins (id, username, password, nickname, status)
SELECT v.id, v.username, v.password, v.nickname, 1
FROM (VALUES
    (1, 'admin', '{noop}admin123', '系统管理员')
) AS v(id, username, password, nickname)
WHERE NOT EXISTS (SELECT 1 FROM admins a WHERE a.id = v.id);

-- 把超级管理员挂到超级管理员角色
INSERT INTO admin_roles (admin_id, role_id)
SELECT 1, 1
WHERE NOT EXISTS (SELECT 1 FROM admin_roles ar WHERE ar.admin_id = 1 AND ar.role_id = 1);

-- 角色-权限：超管 = 全部权限；商品管理员 = 商品权限；订单管理员 = 订单权限
INSERT INTO role_permissions (role_id, permission_id)
SELECT 1, p.id FROM permissions p
WHERE NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = 1 AND rp.permission_id = p.id);

INSERT INTO role_permissions (role_id, permission_id)
SELECT 2, p.id FROM permissions p
WHERE p.code LIKE 'product:%'
  AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = 2 AND rp.permission_id = p.id);

INSERT INTO role_permissions (role_id, permission_id)
SELECT 3, p.id FROM permissions p
WHERE p.code LIKE 'order:%'
  AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = 3 AND rp.permission_id = p.id);

-- ------------------------------------------------------------
-- 九、序列校准（★ 必需，漏了它业务 INSERT 必然主键冲突）
-- ------------------------------------------------------------
-- 上面的种子数据全是"显式指定 id"插入的，而 PostgreSQL 的序列**不会因此前进** ——
-- 序列仍停在初始值，表里却已经有 id = 1..N 的数据。
-- 后果：业务侧第一次 INSERT 时 DEFAULT nextval(...) 吐出 2（或 1），直接撞已有主键：
--   ERROR: duplicate key value violates unique constraint "products_pkey"
-- 所以必须把每个序列推到「当前最大 id」，COALESCE 兜住"表为空"的极端情况。
--
-- 这 8 张表都是显式指定 id 插入的：categories / brands / products /
-- product_skus / users / roles / permissions / admins。
-- （product_images、inventories、admin_roles、role_permissions 没指定 id，无需校准。）
SELECT setval(pg_get_serial_sequence('categories',   'id'), COALESCE((SELECT MAX(id) FROM categories),   1));
SELECT setval(pg_get_serial_sequence('brands',       'id'), COALESCE((SELECT MAX(id) FROM brands),       1));
SELECT setval(pg_get_serial_sequence('products',     'id'), COALESCE((SELECT MAX(id) FROM products),     1));
SELECT setval(pg_get_serial_sequence('product_skus', 'id'), COALESCE((SELECT MAX(id) FROM product_skus), 1));
SELECT setval(pg_get_serial_sequence('users',        'id'), COALESCE((SELECT MAX(id) FROM users),        1));
SELECT setval(pg_get_serial_sequence('roles',        'id'), COALESCE((SELECT MAX(id) FROM roles),        1));
SELECT setval(pg_get_serial_sequence('permissions',  'id'), COALESCE((SELECT MAX(id) FROM permissions),  1));
SELECT setval(pg_get_serial_sequence('admins',       'id'), COALESCE((SELECT MAX(id) FROM admins),       1));
