# Day 03：PostgreSQL 数据库设计

> 项目：MallX 企业级 B2C 电商系统  
> 今天目标：把 MallX 的业务需求转换成真正可以使用的 PostgreSQL 数据库。

---

# 一、今天要完成什么？

今天主要解决一个问题：

> **MallX 到底需要哪些数据库表？这些表之间是什么关系？**

今天完成：

- [ ] 确定数据库设计原则
- [ ] 确定表命名规范
- [ ] 设计用户表
- [ ] 设计地址表
- [ ] 设计商品表
- [ ] 设计分类和品牌表
- [ ] 设计 SPU / SKU
- [ ] 设计库存表
- [ ] 设计购物车表
- [ ] 设计订单表
- [ ] 设计支付表
- [ ] 设计评价表
- [ ] 设计售后表
- [ ] 设计优惠券表
- [ ] 设计 RBAC 权限表
- [ ] 设计索引
- [ ] 设计 PostgreSQL 搜索字段
- [ ] 创建数据库
- [ ] 编写第一版 SQL

---

# 二、数据库使用 PostgreSQL

MallX 使用：

```text
PostgreSQL
```

数据库名称：

```text
mallx
```

创建数据库：

```sql
CREATE DATABASE mallx;
```

连接：

```text
Host: localhost
Port: 5432
Database: mallx
Username: postgres
Password: 你的密码
```

---

# 三、为什么使用 PostgreSQL？

MallX 不只是把 PostgreSQL 当成普通关系型数据库。

我们还会使用 PostgreSQL 的一些高级能力：

```text
PostgreSQL
│
├── 普通关系型数据库
│
├── JSONB
│
├── Full Text Search
│
├── pg_trgm
│
├── GIN
│
└── GiST
```

这样第一版可以：

> **使用 PostgreSQL 的搜索能力代替 Elasticsearch。**

例如商品搜索：

```text
用户输入：

苹果手机
```

数据库可以根据：

```text
商品名称
商品描述
商品关键词
商品标签
```

进行搜索。

---

# 四、数据库设计原则

MallX 遵循几个简单原则。

## 1. 表名统一使用小写

例如：

```text
users
products
orders
order_items
```

不要：

```text
Users
Products
Orders
```

---

## 2. 多个单词使用下划线

例如：

```text
user_addresses
order_items
product_categories
```

---

## 3. 主键统一使用 id

例如：

```sql
id BIGINT PRIMARY KEY
```

---

## 4. 创建时间和更新时间统一

大部分业务表包含：

```text
created_at
updated_at
```

例如：

```sql
created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
```

---

## 5. 不直接删除重要业务数据

例如订单：

```text
订单创建
    ↓
订单支付
    ↓
订单发货
    ↓
订单完成
```

一般不会直接：

```sql
DELETE FROM orders;
```

而是通过状态控制。

例如：

```text
status = CANCELLED
```

---

# 五、数据库整体结构

MallX 的数据库大致分成：

```text
mallx
│
├── 用户
│   ├── users
│   └── user_addresses
│
├── 商品
│   ├── categories
│   ├── brands
│   ├── products
│   ├── product_skus
│   └── product_images
│
├── 库存
│   ├── inventories
│   └── inventory_logs
│
├── 购物车
│   └── cart_items
│
├── 订单
│   ├── orders
│   └── order_items
│
├── 支付
│   └── payments
│
├── 评价
│   └── reviews
│
├── 售后
│   └── after_sales
│
├── 营销
│   ├── coupons
│   └── user_coupons
│
└── RBAC
    ├── admins
    ├── roles
    ├── permissions
    ├── admin_roles
    └── role_permissions
```

---

# 六、用户模块

## 6.1 users

用户表。

```sql
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,

    username VARCHAR(50) NOT NULL UNIQUE,

    password VARCHAR(255) NOT NULL,

    nickname VARCHAR(50),

    phone VARCHAR(20) UNIQUE,

    email VARCHAR(100) UNIQUE,

    avatar VARCHAR(500),

    status SMALLINT NOT NULL DEFAULT 1,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

主要字段：

| 字段 | 说明 |
|---|---|
| id | 用户 ID |
| username | 用户名 |
| password | 加密后的密码 |
| nickname | 昵称 |
| phone | 手机号 |
| email | 邮箱 |
| avatar | 头像 |
| status | 用户状态 |
| created_at | 创建时间 |
| updated_at | 更新时间 |

---

# 七、用户地址

## 7.1 user_addresses

一个用户可以拥有多个收货地址。

关系：

```text
users
  │
  └── user_addresses
```

```sql
CREATE TABLE user_addresses (
    id BIGSERIAL PRIMARY KEY,

    user_id BIGINT NOT NULL,

    receiver_name VARCHAR(50) NOT NULL,

    receiver_phone VARCHAR(20) NOT NULL,

    province VARCHAR(50) NOT NULL,

    city VARCHAR(50) NOT NULL,

    district VARCHAR(50) NOT NULL,

    detail_address VARCHAR(255) NOT NULL,

    is_default BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_user_address_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
);
```

---

# 八、商品模块

商品系统是整个电商系统最重要的部分之一。

这里需要理解：

```text
分类
品牌
SPU
SKU
商品图片
```

---

# 九、商品分类

## 9.1 categories

例如：

```text
手机
├── Apple
├── Huawei
├── Xiaomi
│
电脑
├── Mac
├── ThinkPad
└── Dell
```

表：

```sql
CREATE TABLE categories (
    id BIGSERIAL PRIMARY KEY,

    parent_id BIGINT,

    name VARCHAR(100) NOT NULL,

    sort_order INT NOT NULL DEFAULT 0,

    status SMALLINT NOT NULL DEFAULT 1,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

这里：

```text
parent_id
```

用于实现分类树。

例如：

```text
手机
  ↓
智能手机
  ↓
游戏手机
```

---

# 十、品牌

## 10.1 brands

```sql
CREATE TABLE brands (
    id BIGSERIAL PRIMARY KEY,

    name VARCHAR(100) NOT NULL UNIQUE,

    logo VARCHAR(500),

    description TEXT,

    status SMALLINT NOT NULL DEFAULT 1,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

例如：

```text
Apple
Huawei
Xiaomi
Samsung
Lenovo
```

---

# 十一、SPU

这里是电商项目中非常重要的概念。

## 什么是 SPU？

SPU 可以理解为：

> 一个商品的大类。

例如：

```text
Apple iPhone 17
```

这是一个 SPU。

---

## 11.1 products

```sql
CREATE TABLE products (
    id BIGSERIAL PRIMARY KEY,

    category_id BIGINT NOT NULL,

    brand_id BIGINT,

    name VARCHAR(200) NOT NULL,

    subtitle VARCHAR(500),

    description TEXT,

    main_image VARCHAR(500),

    status SMALLINT NOT NULL DEFAULT 0,

    search_vector TSVECTOR,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_product_category
        FOREIGN KEY (category_id)
        REFERENCES categories(id),

    CONSTRAINT fk_product_brand
        FOREIGN KEY (brand_id)
        REFERENCES brands(id)
);
```

---

# 十二、SKU

## 什么是 SKU？

SKU 是真正可以购买的商品规格。

例如：

```text
iPhone 17
│
├── 黑色 256GB
├── 黑色 512GB
├── 白色 256GB
└── 白色 512GB
```

其中：

```text
iPhone 17
```

是 SPU。

而：

```text
黑色 + 256GB
```

是 SKU。

---

# 十三、product_skus

```sql
CREATE TABLE product_skus (
    id BIGSERIAL PRIMARY KEY,

    product_id BIGINT NOT NULL,

    sku_code VARCHAR(100) NOT NULL UNIQUE,

    name VARCHAR(200),

    price NUMERIC(12,2) NOT NULL,

    original_price NUMERIC(12,2),

    attributes JSONB,

    image VARCHAR(500),

    status SMALLINT NOT NULL DEFAULT 1,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_sku_product
        FOREIGN KEY (product_id)
        REFERENCES products(id)
);
```

这里使用了：

```text
JSONB
```

保存 SKU 属性。

例如：

```json
{
  "color": "黑色",
  "storage": "256GB"
}
```

PostgreSQL 的 JSONB 非常适合这种动态商品属性。

---

# 十四、商品图片

## 14.1 product_images

```sql
CREATE TABLE product_images (
    id BIGSERIAL PRIMARY KEY,

    product_id BIGINT NOT NULL,

    image_url VARCHAR(500) NOT NULL,

    sort_order INT NOT NULL DEFAULT 0,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_product_image_product
        FOREIGN KEY (product_id)
        REFERENCES products(id)
);
```

图片实际文件以后放：

```text
Alibaba Cloud OSS
```

数据库只保存：

```text
image_url
```

---

# 十五、库存模块

## 15.1 inventories

一个 SKU 对应一个库存记录。

```sql
CREATE TABLE inventories (
    id BIGSERIAL PRIMARY KEY,

    sku_id BIGINT NOT NULL UNIQUE,

    total_stock INT NOT NULL DEFAULT 0,

    available_stock INT NOT NULL DEFAULT 0,

    locked_stock INT NOT NULL DEFAULT 0,

    sold_stock INT NOT NULL DEFAULT 0,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_inventory_sku
        FOREIGN KEY (sku_id)
        REFERENCES product_skus(id)
);
```

库存：

```text
total_stock
     │
     ├── available_stock
     │
     └── locked_stock
```

例如：

```text
总库存：100

可用库存：95

锁定库存：5
```

---

# 十六、库存日志

## 16.1 inventory_logs

用于记录库存变化。

```sql
CREATE TABLE inventory_logs (
    id BIGSERIAL PRIMARY KEY,

    sku_id BIGINT NOT NULL,

    change_quantity INT NOT NULL,

    before_stock INT NOT NULL,

    after_stock INT NOT NULL,

    type VARCHAR(50) NOT NULL,

    reference_id BIGINT,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

例如：

```text
用户购买 2 件

100
 ↓
98
```

记录：

```text
before_stock = 100
after_stock = 98
change_quantity = -2
```

---

# 十七、购物车

## 17.1 cart_items

```sql
CREATE TABLE cart_items (
    id BIGSERIAL PRIMARY KEY,

    user_id BIGINT NOT NULL,

    sku_id BIGINT NOT NULL,

    quantity INT NOT NULL DEFAULT 1,

    selected BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_cart_user
        FOREIGN KEY (user_id)
        REFERENCES users(id),

    CONSTRAINT fk_cart_sku
        FOREIGN KEY (sku_id)
        REFERENCES product_skus(id),

    CONSTRAINT uk_cart_user_sku
        UNIQUE (user_id, sku_id)
);
```

一个用户：

```text
user_id = 1
```

可以有：

```text
SKU 1001
SKU 1002
SKU 1003
```

---

# 十八、订单模块

订单是电商系统的核心。

---

# 十九、orders

```sql
CREATE TABLE orders (
    id BIGSERIAL PRIMARY KEY,

    order_no VARCHAR(50) NOT NULL UNIQUE,

    user_id BIGINT NOT NULL,

    total_amount NUMERIC(12,2) NOT NULL,

    pay_amount NUMERIC(12,2) NOT NULL,

    status VARCHAR(30) NOT NULL,

    receiver_name VARCHAR(50) NOT NULL,

    receiver_phone VARCHAR(20) NOT NULL,

    receiver_address VARCHAR(500) NOT NULL,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    paid_at TIMESTAMP,

    shipped_at TIMESTAMP,

    completed_at TIMESTAMP,

    cancelled_at TIMESTAMP,

    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_order_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
);
```

订单状态：

```text
PENDING_PAYMENT
        ↓
PAID
        ↓
SHIPPED
        ↓
COMPLETED
```

取消：

```text
PENDING_PAYMENT
        ↓
CANCELLED
```

---

# 二十、订单明细

## 20.1 order_items

一个订单可以有多个商品。

```sql
CREATE TABLE order_items (
    id BIGSERIAL PRIMARY KEY,

    order_id BIGINT NOT NULL,

    product_id BIGINT NOT NULL,

    sku_id BIGINT NOT NULL,

    product_name VARCHAR(200) NOT NULL,

    sku_name VARCHAR(200),

    price NUMERIC(12,2) NOT NULL,

    quantity INT NOT NULL,

    total_amount NUMERIC(12,2) NOT NULL,

    image VARCHAR(500),

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_order_item_order
        FOREIGN KEY (order_id)
        REFERENCES orders(id)
);
```

例如：

```text
订单 10001

├── iPhone × 1
├── AirPods × 2
└── 手机壳 × 1
```

对应：

```text
orders
   │
   ├── order_item
   ├── order_item
   └── order_item
```

---

# 二十一、支付模块

## 21.1 payments

V1.0 暂时使用模拟支付。

```sql
CREATE TABLE payments (
    id BIGSERIAL PRIMARY KEY,

    payment_no VARCHAR(50) NOT NULL UNIQUE,

    order_id BIGINT NOT NULL,

    amount NUMERIC(12,2) NOT NULL,

    method VARCHAR(30) NOT NULL,

    status VARCHAR(30) NOT NULL,

    paid_at TIMESTAMP,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_payment_order
        FOREIGN KEY (order_id)
        REFERENCES orders(id)
);
```

支付状态：

```text
WAITING
   ↓
SUCCESS
```

或者：

```text
WAITING
   ↓
FAILED
```

---

# 二十二、评价模块

## 22.1 reviews

```sql
CREATE TABLE reviews (
    id BIGSERIAL PRIMARY KEY,

    user_id BIGINT NOT NULL,

    product_id BIGINT NOT NULL,

    order_id BIGINT NOT NULL,

    order_item_id BIGINT,

    rating SMALLINT NOT NULL,

    content TEXT,

    images JSONB,

    status SMALLINT NOT NULL DEFAULT 1,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

评价图片：

```json
[
  "https://xxx/image1.jpg",
  "https://xxx/image2.jpg"
]
```

---

# 二十三、售后模块

## 23.1 after_sales

```sql
CREATE TABLE after_sales (
    id BIGSERIAL PRIMARY KEY,

    after_sale_no VARCHAR(50) NOT NULL UNIQUE,

    order_id BIGINT NOT NULL,

    order_item_id BIGINT,

    user_id BIGINT NOT NULL,

    type VARCHAR(30) NOT NULL,

    reason VARCHAR(500),

    amount NUMERIC(12,2),

    status VARCHAR(30) NOT NULL,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

售后类型：

```text
REFUND
RETURN
EXCHANGE
```

---

# 二十四、优惠券

## 24.1 coupons

```sql
CREATE TABLE coupons (
    id BIGSERIAL PRIMARY KEY,

    name VARCHAR(100) NOT NULL,

    type VARCHAR(30) NOT NULL,

    discount_amount NUMERIC(12,2),

    discount_rate NUMERIC(5,2),

    min_amount NUMERIC(12,2),

    total_count INT NOT NULL DEFAULT 0,

    received_count INT NOT NULL DEFAULT 0,

    start_time TIMESTAMP NOT NULL,

    end_time TIMESTAMP NOT NULL,

    status SMALLINT NOT NULL DEFAULT 1,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

---

# 二十五、用户优惠券

## 25.1 user_coupons

```sql
CREATE TABLE user_coupons (
    id BIGSERIAL PRIMARY KEY,

    user_id BIGINT NOT NULL,

    coupon_id BIGINT NOT NULL,

    status VARCHAR(30) NOT NULL DEFAULT 'UNUSED',

    received_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    used_at TIMESTAMP,

    order_id BIGINT
);
```

状态：

```text
UNUSED
USED
EXPIRED
```

---

# 二十六、RBAC 权限系统

MallX 使用：

```text
RBAC
```

也就是：

```text
User
 ↓
Role
 ↓
Permission
```

管理端管理员：

```text
管理员
  ↓
角色
  ↓
权限
```

---

# 二十七、admins

```sql
CREATE TABLE admins (
    id BIGSERIAL PRIMARY KEY,

    username VARCHAR(50) NOT NULL UNIQUE,

    password VARCHAR(255) NOT NULL,

    nickname VARCHAR(50),

    status SMALLINT NOT NULL DEFAULT 1,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

---

# 二十八、roles

```sql
CREATE TABLE roles (
    id BIGSERIAL PRIMARY KEY,

    name VARCHAR(50) NOT NULL,

    code VARCHAR(50) NOT NULL UNIQUE,

    description VARCHAR(255),

    status SMALLINT NOT NULL DEFAULT 1,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

例如：

```text
SUPER_ADMIN
PRODUCT_ADMIN
ORDER_ADMIN
USER_ADMIN
```

---

# 二十九、permissions

```sql
CREATE TABLE permissions (
    id BIGSERIAL PRIMARY KEY,

    name VARCHAR(100) NOT NULL,

    code VARCHAR(100) NOT NULL UNIQUE,

    type VARCHAR(30) NOT NULL,

    path VARCHAR(255),

    method VARCHAR(20),

    parent_id BIGINT,

    status SMALLINT NOT NULL DEFAULT 1,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

例如：

```text
product:create
product:update
product:delete
product:list
order:list
order:ship
user:list
```

---

# 三十、管理员角色关系

## 30.1 admin_roles

```sql
CREATE TABLE admin_roles (
    admin_id BIGINT NOT NULL,

    role_id BIGINT NOT NULL,

    PRIMARY KEY (admin_id, role_id)
);
```

---

# 三十一、角色权限关系

## 31.1 role_permissions

```sql
CREATE TABLE role_permissions (
    role_id BIGINT NOT NULL,

    permission_id BIGINT NOT NULL,

    PRIMARY KEY (role_id, permission_id)
);
```

最终：

```text
Admin
  │
  ↓
AdminRole
  │
  ↓
Role
  │
  ↓
RolePermission
  │
  ↓
Permission
```

---

# 三十二、数据库核心关系

MallX 最重要的关系：

```text
User
 │
 ├── Address
 │
 ├── Cart
 │
 ├── Order
 │      │
 │      └── OrderItem
 │               │
 │               └── SKU
 │
 └── Review


Category
 │
 └── Product
        │
        ├── ProductImage
        │
        └── SKU
              │
              └── Inventory
```

商品部分：

```text
Category
    │
    ↓
Product
    │
    ├────────→ ProductImage
    │
    └────────→ ProductSKU
                   │
                   ↓
               Inventory
```

订单部分：

```text
User
 │
 ↓
Order
 │
 ├── OrderItem
 │       │
 │       └── SKU
 │
 └── Payment
```

---

# 三十三、索引设计

数据库不能只设计表。

还需要考虑：

> **查询速度。**

---

## 33.1 用户索引

```sql
CREATE INDEX idx_users_phone
ON users(phone);

CREATE INDEX idx_users_email
ON users(email);
```

---

## 33.2 商品索引

```sql
CREATE INDEX idx_products_category_id
ON products(category_id);

CREATE INDEX idx_products_brand_id
ON products(brand_id);

CREATE INDEX idx_products_status
ON products(status);
```

---

## 33.3 SKU 索引

```sql
CREATE INDEX idx_product_skus_product_id
ON product_skus(product_id);
```

---

## 33.4 订单索引

```sql
CREATE INDEX idx_orders_user_id
ON orders(user_id);

CREATE INDEX idx_orders_status
ON orders(status);

CREATE INDEX idx_orders_created_at
ON orders(created_at);
```

---

# 三十四、JSONB 索引

SKU：

```text
attributes
```

是：

```text
JSONB
```

可以建立 GIN 索引：

```sql
CREATE INDEX idx_product_skus_attributes
ON product_skus
USING GIN (attributes);
```

例如：

```json
{
  "color": "black",
  "storage": "256GB"
}
```

以后可以查询：

```sql
SELECT *
FROM product_skus
WHERE attributes @> '{"color":"black"}';
```

---

# 三十五、商品全文搜索

PostgreSQL 可以使用：

```text
tsvector
```

保存搜索向量。

products：

```text
search_vector
```

建立 GIN：

```sql
CREATE INDEX idx_products_search
ON products
USING GIN (search_vector);
```

搜索：

```sql
SELECT *
FROM products
WHERE search_vector @@
      plainto_tsquery('simple', 'iphone');
```

---

# 三十六、pg_trgm

除了全文搜索，还可以使用：

```text
pg_trgm
```

解决模糊搜索。

启用：

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

例如：

```sql
CREATE INDEX idx_products_name_trgm
ON products
USING GIN (name gin_trgm_ops);
```

可以用于：

```sql
SELECT *
FROM products
WHERE name ILIKE '%iphone%';
```

---

# 三十七、为什么同时使用 FTS + pg_trgm？

两者解决的问题不完全一样。

```text
Full Text Search
    ↓
更适合：
关键词搜索
分词
相关性搜索

pg_trgm
    ↓
更适合：
模糊匹配
LIKE / ILIKE
输入错误
部分字符串
```

MallX 可以组合：

```text
用户搜索
    │
    ├── FTS
    │
    └── pg_trgm
          ↓
       商品结果
```

这样第一版不需要 Elasticsearch。

---

# 三十八、完整表清单

目前 MallX V1.0 数据库：

| 模块 | 表 |
|---|---|
| 用户 | users |
| 用户 | user_addresses |
| 商品 | categories |
| 商品 | brands |
| 商品 | products |
| 商品 | product_skus |
| 商品 | product_images |
| 库存 | inventories |
| 库存 | inventory_logs |
| 购物车 | cart_items |
| 订单 | orders |
| 订单 | order_items |
| 支付 | payments |
| 评价 | reviews |
| 售后 | after_sales |
| 营销 | coupons |
| 营销 | user_coupons |
| RBAC | admins |
| RBAC | roles |
| RBAC | permissions |
| RBAC | admin_roles |
| RBAC | role_permissions |

总计：

```text
22 张核心表
```

---

# 三十九、数据库目录

建议把 SQL 单独放到：

```text
backend/
└── sql/
    ├── 01-schema.sql
    ├── 02-index.sql
    └── 03-data.sql
```

以后：

```text
01-schema.sql
```

负责建表。

```text
02-index.sql
```

负责索引。

```text
03-data.sql
```

负责初始化数据。

---

# 四十、推荐的 SQL 执行顺序

不要随便执行。

按照：

```text
1. 创建数据库
       ↓
2. 创建 PostgreSQL Extension
       ↓
3. 创建基础表
       ↓
4. 创建商品表
       ↓
5. 创建库存表
       ↓
6. 创建订单表
       ↓
7. 创建支付/评价/售后
       ↓
8. 创建营销表
       ↓
9. 创建 RBAC
       ↓
10. 创建索引
       ↓
11. 插入初始化数据
```

---

# 四十一、今天先不要追求完美

Day 3 的数据库设计是：

```text
V1.0
```

以后开发过程中可能会修改。

例如：

```text
Day 3
数据库设计
    ↓
Day 8
分类/品牌
    ↓
Day 9
SPU/SKU
    ↓
Day 10
搜索
    ↓
发现需要增加字段
    ↓
修改数据库
```

这是正常的。

真正的项目数据库不是一开始就 100% 完美。

---

# 四十二、今天的最终目标

完成 Day 3 后，你应该能够理解：

```text
用户
 ↓
地址
 ↓
商品
 ↓
SKU
 ↓
库存
 ↓
购物车
 ↓
订单
 ↓
支付
 ↓
评价
 ↓
售后
```

同时：

```text
管理员
 ↓
角色
 ↓
权限
```

并且知道：

```text
SPU 是什么
SKU 是什么
JSONB 是什么
GIN 是什么
全文搜索是什么
pg_trgm 是什么
索引为什么需要建立
```

---

# 四十三、Day 3 验收标准

## 数据库

- [ ] PostgreSQL 已安装
- [ ] mallx 数据库创建成功
- [ ] 22 张核心表创建成功
- [ ] 外键关系正确
- [ ] 唯一约束正确
- [ ] 索引创建成功

## PostgreSQL

- [ ] JSONB 可以正常使用
- [ ] pg_trgm 扩展启用成功
- [ ] GIN 索引创建成功
- [ ] `search_vector` 创建成功

## 项目

最终目录：

```text
MallX/
├── backend/
│   ├── mallx/
│   └── sql/
│       ├── 01-schema.sql
│       ├── 02-index.sql
│       └── 03-data.sql
│
├── frontend/
│
├── docs/
│   └── daily/
│       ├── Day-01-项目需求与技术选型.md
│       ├── Day-02-系统架构与项目初始化.md
│       └── Day-03-PostgreSQL数据库设计.md
│
└── README.md
```

---

# 四十四、Day 3 完成

今天我们完成的是：

```text
业务需求
    ↓
数据库设计
    ↓
22 张核心表
    ↓
表之间的关系
    ↓
索引
    ↓
PostgreSQL 高级功能
```

下一步进入：

> **Day 04：后端基础设施**

开始真正写 Java 代码：

```text
Spring Boot
    ↓
MyBatis-Plus
    ↓
PostgreSQL
    ↓
统一返回结果
    ↓
统一异常处理
    ↓
全局配置
    ↓
日志
    ↓
Swagger
```

到 Day 4 开始，MallX 就正式从“设计阶段”进入“编码阶段”。