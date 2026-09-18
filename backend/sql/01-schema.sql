-- ============================================================
-- MallX 数据库表结构（Day 03）
-- 数据库：mallx（PostgreSQL 16）
-- 说明：
--   - 22 张核心表
--   - 表名小写 + 下划线；主键统一为 id BIGSERIAL
--   - 业务表含 created_at / updated_at
--   - 该脚本可重复执行（幂等），可直接在 mallx 库中运行
-- 执行前请确保已连接 mallx 库：\c mallx
-- ============================================================

-- ------------------------------------------------------------
-- 0. 启用扩展（幂等）
-- ------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================
-- 一、用户模块
-- ============================================================

-- 1. 用户表
CREATE TABLE IF NOT EXISTS users (
    id          BIGSERIAL PRIMARY KEY,
    username    VARCHAR(50)  NOT NULL UNIQUE,
    password    VARCHAR(255) NOT NULL,
    nickname    VARCHAR(50),
    phone       VARCHAR(20)  UNIQUE,
    email       VARCHAR(100) UNIQUE,
    avatar      VARCHAR(500),
    status      SMALLINT     NOT NULL DEFAULT 1,
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2. 用户收货地址
CREATE TABLE IF NOT EXISTS user_addresses (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT       NOT NULL,
    receiver_name   VARCHAR(50)  NOT NULL,
    receiver_phone  VARCHAR(20)  NOT NULL,
    province        VARCHAR(50)  NOT NULL,
    city            VARCHAR(50)  NOT NULL,
    district        VARCHAR(50)  NOT NULL,
    detail_address  VARCHAR(255) NOT NULL,
    is_default      BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_user_address_user
        FOREIGN KEY (user_id) REFERENCES users(id)
);

-- ============================================================
-- 二、商品模块（分类 / 品牌 / SPU / SKU / 商品图）
-- ============================================================

-- 3. 商品分类（parent_id 支持多级分类树）
CREATE TABLE IF NOT EXISTS categories (
    id          BIGSERIAL PRIMARY KEY,
    parent_id   BIGINT,
    name        VARCHAR(100) NOT NULL,
    sort_order  INT          NOT NULL DEFAULT 0,
    status      SMALLINT     NOT NULL DEFAULT 1,
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 4. 品牌
CREATE TABLE IF NOT EXISTS brands (
    id          BIGSERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,
    logo        VARCHAR(500),
    description TEXT,
    status      SMALLINT     NOT NULL DEFAULT 1,
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 5. 商品 SPU（search_vector 用于全文搜索，见下方触发器自动维护）
CREATE TABLE IF NOT EXISTS products (
    id            BIGSERIAL PRIMARY KEY,
    category_id   BIGINT       NOT NULL,
    brand_id      BIGINT,
    name          VARCHAR(200) NOT NULL,
    subtitle      VARCHAR(500),
    description   TEXT,
    main_image    VARCHAR(500),
    status        SMALLINT     NOT NULL DEFAULT 0,
    is_deleted    SMALLINT     NOT NULL DEFAULT 0,      -- ★ Day 09：0=正常 1=已删除（软删除）
    search_vector TSVECTOR,
    created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_product_category FOREIGN KEY (category_id) REFERENCES categories(id),
    CONSTRAINT fk_product_brand    FOREIGN KEY (brand_id)    REFERENCES brands(id)
);

-- 6. 商品 SKU（attributes 用 JSONB 存动态规格）
CREATE TABLE IF NOT EXISTS product_skus (
    id              BIGSERIAL PRIMARY KEY,
    product_id      BIGINT        NOT NULL,
    sku_code        VARCHAR(100)  NOT NULL UNIQUE,
    name            VARCHAR(200),
    price           NUMERIC(12,2) NOT NULL,
    original_price  NUMERIC(12,2),
    attributes      JSONB,
    image           VARCHAR(500),
    status          SMALLINT      NOT NULL DEFAULT 1,
    is_deleted      SMALLINT      NOT NULL DEFAULT 0,    -- ★ Day 09：0=正常 1=已删除（软删除）
    created_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_sku_product FOREIGN KEY (product_id) REFERENCES products(id)
);

-- 7. 商品图片（OSS 只存 URL）
CREATE TABLE IF NOT EXISTS product_images (
    id          BIGSERIAL PRIMARY KEY,
    product_id  BIGINT       NOT NULL,
    image_url   VARCHAR(500) NOT NULL,
    sort_order  INT          NOT NULL DEFAULT 0,
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_product_image_product FOREIGN KEY (product_id) REFERENCES products(id)
);

-- ============================================================
-- 三、库存模块
-- ============================================================

-- 8. 库存（一 SKU 一库存）
CREATE TABLE IF NOT EXISTS inventories (
    id               BIGSERIAL PRIMARY KEY,
    sku_id           BIGINT    NOT NULL UNIQUE,
    total_stock      INT       NOT NULL DEFAULT 0,
    available_stock  INT       NOT NULL DEFAULT 0,
    locked_stock     INT       NOT NULL DEFAULT 0,
    sold_stock       INT       NOT NULL DEFAULT 0,
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_inventory_sku FOREIGN KEY (sku_id) REFERENCES product_skus(id)
);

-- 9. 库存日志
CREATE TABLE IF NOT EXISTS inventory_logs (
    id               BIGSERIAL PRIMARY KEY,
    sku_id           BIGINT      NOT NULL,
    change_quantity  INT         NOT NULL,
    before_stock     INT         NOT NULL,
    after_stock      INT         NOT NULL,
    type             VARCHAR(50) NOT NULL,
    reference_id     BIGINT,
    created_at       TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 四、购物车模块
-- ============================================================

-- 10. 购物车项
CREATE TABLE IF NOT EXISTS cart_items (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT    NOT NULL,
    sku_id      BIGINT    NOT NULL,
    quantity    INT       NOT NULL DEFAULT 1,
    selected    BOOLEAN   NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_cart_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_cart_sku  FOREIGN KEY (sku_id)  REFERENCES product_skus(id),
    CONSTRAINT uk_cart_user_sku UNIQUE (user_id, sku_id)
);

-- ============================================================
-- 五、订单模块
-- ============================================================

-- 11. 订单
CREATE TABLE IF NOT EXISTS orders (
    id                BIGSERIAL PRIMARY KEY,
    order_no          VARCHAR(50)  NOT NULL UNIQUE,
    user_id           BIGINT       NOT NULL,
    total_amount      NUMERIC(12,2) NOT NULL,
    pay_amount        NUMERIC(12,2) NOT NULL,
    status            VARCHAR(30)  NOT NULL,
    receiver_name     VARCHAR(50)  NOT NULL,
    receiver_phone    VARCHAR(20)  NOT NULL,
    receiver_address  VARCHAR(500) NOT NULL,
    created_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    paid_at           TIMESTAMP,
    shipped_at        TIMESTAMP,
    completed_at      TIMESTAMP,
    cancelled_at      TIMESTAMP,
    updated_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_order_user FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 12. 订单明细
CREATE TABLE IF NOT EXISTS order_items (
    id             BIGSERIAL PRIMARY KEY,
    order_id       BIGINT        NOT NULL,
    product_id     BIGINT        NOT NULL,
    sku_id         BIGINT        NOT NULL,
    product_name   VARCHAR(200)  NOT NULL,
    sku_name       VARCHAR(200),
    price          NUMERIC(12,2) NOT NULL,
    quantity       INT           NOT NULL,
    total_amount   NUMERIC(12,2) NOT NULL,
    image          VARCHAR(500),
    created_at     TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_order_item_order FOREIGN KEY (order_id) REFERENCES orders(id)
);

-- ============================================================
-- 六、支付模块
-- ============================================================

-- 13. 支付（V1.0 模拟支付）
CREATE TABLE IF NOT EXISTS payments (
    id          BIGSERIAL PRIMARY KEY,
    payment_no  VARCHAR(50)   NOT NULL UNIQUE,
    order_id    BIGINT        NOT NULL,
    amount      NUMERIC(12,2) NOT NULL,
    method      VARCHAR(30)   NOT NULL,
    status      VARCHAR(30)   NOT NULL,
    paid_at     TIMESTAMP,
    created_at  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_payment_order FOREIGN KEY (order_id) REFERENCES orders(id)
);

-- ============================================================
-- 七、评价模块
-- ============================================================

-- 14. 商品评价
CREATE TABLE IF NOT EXISTS reviews (
    id             BIGSERIAL PRIMARY KEY,
    user_id        BIGINT     NOT NULL,
    product_id     BIGINT     NOT NULL,
    order_id       BIGINT     NOT NULL,
    order_item_id  BIGINT,
    rating         SMALLINT   NOT NULL,
    content        TEXT,
    images         JSONB,
    status         SMALLINT   NOT NULL DEFAULT 1,
    created_at     TIMESTAMP  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_review_user    FOREIGN KEY (user_id)    REFERENCES users(id),
    CONSTRAINT fk_review_product FOREIGN KEY (product_id) REFERENCES products(id),
    CONSTRAINT fk_review_order   FOREIGN KEY (order_id)   REFERENCES orders(id)
);

-- ============================================================
-- 八、售后模块
-- ============================================================

-- 15. 售后申请
CREATE TABLE IF NOT EXISTS after_sales (
    id              BIGSERIAL PRIMARY KEY,
    after_sale_no   VARCHAR(50)   NOT NULL UNIQUE,
    order_id        BIGINT        NOT NULL,
    order_item_id   BIGINT,
    user_id         BIGINT        NOT NULL,
    type            VARCHAR(30)   NOT NULL,
    reason          VARCHAR(500),
    amount          NUMERIC(12,2),
    status          VARCHAR(30)   NOT NULL,
    created_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_after_sale_order FOREIGN KEY (order_id) REFERENCES orders(id),
    CONSTRAINT fk_after_sale_user  FOREIGN KEY (user_id)  REFERENCES users(id)
);

-- ============================================================
-- 九、营销模块
-- ============================================================

-- 16. 优惠券
CREATE TABLE IF NOT EXISTS coupons (
    id               BIGSERIAL PRIMARY KEY,
    name             VARCHAR(100)  NOT NULL,
    type             VARCHAR(30)   NOT NULL,
    discount_amount  NUMERIC(12,2),
    discount_rate    NUMERIC(5,2),
    min_amount       NUMERIC(12,2),
    total_count      INT           NOT NULL DEFAULT 0,
    received_count   INT           NOT NULL DEFAULT 0,
    start_time       TIMESTAMP     NOT NULL,
    end_time         TIMESTAMP     NOT NULL,
    status           SMALLINT      NOT NULL DEFAULT 1,
    created_at       TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 17. 用户优惠券
CREATE TABLE IF NOT EXISTS user_coupons (
    id            BIGSERIAL PRIMARY KEY,
    user_id       BIGINT      NOT NULL,
    coupon_id     BIGINT      NOT NULL,
    status        VARCHAR(30) NOT NULL DEFAULT 'UNUSED',
    received_at   TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    used_at       TIMESTAMP,
    order_id      BIGINT,
    CONSTRAINT fk_user_coupon_user   FOREIGN KEY (user_id)   REFERENCES users(id),
    CONSTRAINT fk_user_coupon_coupon FOREIGN KEY (coupon_id) REFERENCES coupons(id)
);

-- ============================================================
-- 十、RBAC 权限模块
-- ============================================================

-- 18. 管理员
CREATE TABLE IF NOT EXISTS admins (
    id          BIGSERIAL PRIMARY KEY,
    username    VARCHAR(50)  NOT NULL UNIQUE,
    password    VARCHAR(255) NOT NULL,
    nickname    VARCHAR(50),
    status      SMALLINT     NOT NULL DEFAULT 1,
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 19. 角色
CREATE TABLE IF NOT EXISTS roles (
    id          BIGSERIAL PRIMARY KEY,
    name        VARCHAR(50)  NOT NULL,
    code        VARCHAR(50)  NOT NULL UNIQUE,
    description VARCHAR(255),
    status      SMALLINT     NOT NULL DEFAULT 1,
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 20. 权限
CREATE TABLE IF NOT EXISTS permissions (
    id          BIGSERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    code        VARCHAR(100) NOT NULL UNIQUE,
    type        VARCHAR(30)  NOT NULL,
    path        VARCHAR(255),
    method      VARCHAR(20),
    parent_id   BIGINT,
    status      SMALLINT     NOT NULL DEFAULT 1,
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 21. 管理员-角色（多对多）
CREATE TABLE IF NOT EXISTS admin_roles (
    admin_id  BIGINT NOT NULL,
    role_id   BIGINT NOT NULL,
    PRIMARY KEY (admin_id, role_id),
    CONSTRAINT fk_admin_role_admin FOREIGN KEY (admin_id) REFERENCES admins(id),
    CONSTRAINT fk_admin_role_role   FOREIGN KEY (role_id)  REFERENCES roles(id)
);

-- 22. 角色-权限（多对多）
CREATE TABLE IF NOT EXISTS role_permissions (
    role_id        BIGINT NOT NULL,
    permission_id  BIGINT NOT NULL,
    PRIMARY KEY (role_id, permission_id),
    CONSTRAINT fk_role_permission_role       FOREIGN KEY (role_id)       REFERENCES roles(id),
    CONSTRAINT fk_role_permission_permission FOREIGN KEY (permission_id) REFERENCES permissions(id)
);

-- ============================================================
-- 十一、search_vector 自动维护
-- 商品 name/subtitle/description 变化时自动重建全文索引向量
-- ============================================================

-- 维护 products.search_vector 的触发器函数
CREATE OR REPLACE FUNCTION products_search_vector_update()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('simple', coalesce(NEW.name, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(NEW.subtitle, '')), 'B') ||
        setweight(to_tsvector('simple', coalesce(NEW.description, '')), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_products_search_vector ON products;
CREATE TRIGGER trg_products_search_vector
    BEFORE INSERT OR UPDATE OF name, subtitle, description
    ON products
    FOR EACH ROW
    EXECUTE FUNCTION products_search_vector_update();

-- ============================================================
-- 十二、软删除列（Day 09 追加）
-- 说明：上面 CREATE TABLE IF NOT EXISTS 对已存在的库不会加列，
--       所以老库要靠这一段 ALTER 补齐；IF NOT EXISTS 保证重复执行不报错。
-- ============================================================

ALTER TABLE products     ADD COLUMN IF NOT EXISTS is_deleted SMALLINT NOT NULL DEFAULT 0;
ALTER TABLE product_skus ADD COLUMN IF NOT EXISTS is_deleted SMALLINT NOT NULL DEFAULT 0;

-- 顺带给查询加索引（列表查询会带 is_deleted = 0）
CREATE INDEX IF NOT EXISTS idx_products_is_deleted     ON products(is_deleted);
CREATE INDEX IF NOT EXISTS idx_product_skus_is_deleted ON product_skus(is_deleted);
