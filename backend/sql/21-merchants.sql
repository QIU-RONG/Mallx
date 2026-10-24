-- ============================================================
-- MallX 商户账号（Day 75）—— 商户后台第 2 层（仅商品域）
--
-- ★ 本层解决：商户用独立账号登录后，只能看到/维护【自己店铺】的商品。
--   权限码复用商品域已有的 product:list / product:detail / product:create /
--   product:update + 字典读接口 category:list / brand:list；
--   数据边界靠 token 里的 SHOP_SCOPE_<id> 权限（见 ShopScope）。
--
-- ★ 本层【不做】：订单/售后按店铺隔离（orders 没有 shop_id，需按明细 join，
--   属下一层）；商户结算/分账；商户自助改店铺信息。
-- ============================================================

CREATE TABLE IF NOT EXISTS merchants (
    id         BIGSERIAL PRIMARY KEY,
    shop_id    BIGINT       NOT NULL REFERENCES shops(id),
    username   VARCHAR(50)  NOT NULL,
    password   VARCHAR(100) NOT NULL,
    name       VARCHAR(50)  NOT NULL,
    status     SMALLINT     NOT NULL DEFAULT 1,
    created_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uk_merchants_username') THEN
        ALTER TABLE merchants ADD CONSTRAINT uk_merchants_username UNIQUE (username);
        RAISE NOTICE '[21] uk_merchants_username created';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uk_merchants_shop') THEN
        -- 一个店铺一个账号：第 2 层不处理「一店多账号」的权限细分
        ALTER TABLE merchants ADD CONSTRAINT uk_merchants_shop UNIQUE (shop_id);
        RAISE NOTICE '[21] uk_merchants_shop created';
    END IF;
END $$;

-- 种子：MallX 自营（shop_id=1）的商户账号
INSERT INTO merchants (shop_id, username, password, name, status)
SELECT 1, 'merchant', '{noop}merchant123', '自营店长', 1
WHERE NOT EXISTS (SELECT 1 FROM merchants WHERE username = 'merchant');

SELECT setval(pg_get_serial_sequence('merchants', 'id'),
              COALESCE((SELECT MAX(id) FROM merchants), 1));

SELECT m.id, m.username, s.name AS shop
  FROM merchants m JOIN shops s ON s.id = m.shop_id
 ORDER BY m.id;
