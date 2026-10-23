-- ============================================================
-- MallX 商户/店铺（Day 64）—— 展示层
-- 说明：需在 01..19 之后执行；幂等，可重复跑。
--
-- ★ 本日只做【展示层】：
--   1) 新建 shops 表；2) products.shop_id 挂店铺；3) C 端商品详情显示店铺名；
--   4) 管理端可维护店铺（列表/新建/编辑）。
--   【不做】商户登录、数据权限隔离、订单拆单、分账结算 —— 那是"多商户交易闭环"，
--   会动订单/支付/库存/售后四条主链路，不是同一件事。
-- ============================================================

-- ------------------------------------------------------------
-- 一、店铺表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS shops (
    id          BIGSERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,
    logo        VARCHAR(500),
    description TEXT,
    status      SMALLINT     NOT NULL DEFAULT 1,
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ★ 名称唯一：与 brands 同一取舍（重名会让「按店名找店」直接失效）
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uk_shops_name') THEN
        ALTER TABLE shops ADD CONSTRAINT uk_shops_name UNIQUE (name);
        RAISE NOTICE '[20] uk_shops_name created';
    ELSE
        RAISE NOTICE '[20] uk_shops_name already exists, skipped';
    END IF;
END $$;

-- ------------------------------------------------------------
-- 二、商品挂店铺
-- ------------------------------------------------------------
-- ★ 可空：历史商品允许没有店铺（平台自营/未归属），不做 NOT NULL 强绑
ALTER TABLE products ADD COLUMN IF NOT EXISTS shop_id BIGINT;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_product_shop') THEN
        ALTER TABLE products
            ADD CONSTRAINT fk_product_shop FOREIGN KEY (shop_id) REFERENCES shops(id);
        RAISE NOTICE '[20] fk_product_shop created';
    ELSE
        RAISE NOTICE '[20] fk_product_shop already exists, skipped';
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_products_shop_id ON products(shop_id);

-- ------------------------------------------------------------
-- 三、种子店铺（幂等）
-- ------------------------------------------------------------
INSERT INTO shops (name, description, status)
SELECT v.name, v.description, 1
FROM (VALUES
    ('Apple 官方旗舰店', 'Apple 全系产品，官方正品'),
    ('小米官方旗舰店',   '小米手机与智能家居'),
    ('MallX 自营',       '平台自营，覆盖华为 / 联想 / 三星 / 大疆')
) AS v(name, description)
WHERE NOT EXISTS (SELECT 1 FROM shops s WHERE s.name = v.name);

-- 按品牌把现有商品分到店铺（只补 NULL，不覆盖人工调整过的归属）
UPDATE products p
   SET shop_id = (SELECT id FROM shops WHERE name = 'Apple 官方旗舰店')
 WHERE p.shop_id IS NULL
   AND p.brand_id = (SELECT id FROM brands WHERE name = 'Apple');

UPDATE products p
   SET shop_id = (SELECT id FROM shops WHERE name = '小米官方旗舰店')
 WHERE p.shop_id IS NULL
   AND p.brand_id = (SELECT id FROM brands WHERE name = 'Xiaomi');

UPDATE products p
   SET shop_id = (SELECT id FROM shops WHERE name = 'MallX 自营')
 WHERE p.shop_id IS NULL;

-- ------------------------------------------------------------
-- 四、权限（49..51）—— 只有超管能维护店铺
-- ------------------------------------------------------------
INSERT INTO permissions (id, name, code, type, path, method)
SELECT v.id, v.name, v.code, v.type, v.path, v.method
FROM (VALUES
    (49, '店铺列表', 'shop:list',   'API', '/api/admin/shops',      'GET'),
    (50, '新建店铺', 'shop:create', 'API', '/api/admin/shops',      'POST'),
    (51, '编辑店铺', 'shop:update', 'API', '/api/admin/shops/*',    'PUT')
) AS v(id, name, code, type, path, method)
WHERE NOT EXISTS (SELECT 1 FROM permissions p WHERE p.code = v.code);

-- 超管拿全部（不限前缀，以后新增也归它）
INSERT INTO role_permissions (role_id, permission_id)
SELECT 1, p.id
FROM permissions p
WHERE NOT EXISTS (SELECT 1 FROM role_permissions rp
                   WHERE rp.role_id = 1 AND rp.permission_id = p.id);

-- ★ 故意不给商品管理员（role 2）与订单管理员（role 3）：店铺是平台资产，
--   改店名/停用店铺等于改整个店铺的门面，属于治理动作。
--   反向对照：op_product 打 POST /api/admin/shops 必须 403。

-- ------------------------------------------------------------
-- 五、序列校准
-- ------------------------------------------------------------
SELECT setval(pg_get_serial_sequence('shops', 'id'),
              COALESCE((SELECT MAX(id) FROM shops), 1));
SELECT setval(pg_get_serial_sequence('permissions', 'id'),
              COALESCE((SELECT MAX(id) FROM permissions), 1));

-- ------------------------------------------------------------
-- 六、自检
-- ------------------------------------------------------------
-- 6.1 店铺与商品归属
SELECT s.id, s.name, count(p.id) AS products
  FROM shops s LEFT JOIN products p ON p.shop_id = s.id
 GROUP BY s.id, s.name ORDER BY s.id;
-- ★ 期望：3 家店，Apple=1、小米=1、自营=其余

-- 6.2 没有商品挂在不存在的店铺上（FK 已保证，这里做一次显式对账）
SELECT count(*) AS orphan_shop_products FROM products p
 WHERE p.shop_id IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM shops s WHERE s.id = p.shop_id);

-- 6.3 权限与分发（应为 3 / 3 / 0 / 0）
SELECT (SELECT count(*) FROM permissions WHERE code LIKE 'shop:%')                        AS shop_perms,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 1 AND p.code LIKE 'shop:%')                                   AS role1_shop,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 2 AND p.code LIKE 'shop:%')                                   AS role2_shop,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 3 AND p.code LIKE 'shop:%')                                   AS role3_shop;

-- 6.4 权限总数（应 = 51）
SELECT count(*) AS permissions_total, max(id) AS max_id FROM permissions;
