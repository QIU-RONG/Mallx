# MallX API 总览

> **本文档由脚本生成，不要手改** —— 数据源两处，缺一不可：
> ① 端点清单 / 鉴权档位 / 权限码 ← 解析 `backend/mallx/**/controller/*.java`
> 的 `@XxxMapping` 与 `@PreAuthorize`，叠加 `SecurityConfig` 白名单；
> ② Tag / 说明文案 ← 运行时 `/v3/api-docs`（快照 `docs/api/openapi.json`）。
>
> 两来源的 `(方法, 路径)` 集合必须**完全相等**，否则脚本报 MISMATCH 并拒绝生成。
>
> 重新生成：`python backend/loadtest/day25-api-inventory.py`
> （需要应用已启动且 `docs/api/openapi.json` 是当前构建导出的快照）

## 〇、统计

| 项 | 数量 |
|---|---|
| 端点总数 | **77** |
| ├ 公开（白名单，无需 token） | 10 |
| ├ 仅需登录（C 端 token） | 26 |
| └ 需权限码（管理端） | 41 |
| 管理端端点（`/api/admin/**`） | 40 |
| 用到的权限码 | 41 个 |

★ **状态码约定**（与《README》§接口约定一致，容易踩）：
Security 层（认证/授权）失败返回**真 HTTP** `401` / `403`；
业务异常与参数校验失败返回 **HTTP 200 + body.code ≠ 200**。
⇒ **判一个业务调用是否成功，必须看 `body.code`，不能只看 HTTP 状态码。**

## 一、公开端点（白名单，先匹配先赢）

| 方法 | 路径 | Tag | 说明 | 鉴权 |
|---|---|---|---|---|
| `POST` | `/api/auth/admin/login` | 管理员认证 | 管理员登录 | 公开 |
| `POST` | `/api/auth/login` | auth-controller |  | 公开 |
| `GET` | `/api/brands` | 品牌 | 品牌字典（C 端，仅启用品牌） | 公开 |
| `GET` | `/api/categories/tree` | 商品分类 | 分类树(含二级子分类) | 公开 |
| `GET` | `/api/coupons` | 优惠券 | 可领券列表（公开，游客可看；只含在有效期内且有余额的券） | 公开 |
| `GET` | `/api/hello` | hello-controller |  | 公开 |
| `GET` | `/api/products` | 商品 | 商品分页列表（上架中，可按分类/关键词过滤） | 公开 |
| `GET` | `/api/products/search` | 商品 | 商品搜索（全文关键词 + 分类 + SKU 属性筛选） | 公开 |
| `GET` | `/api/products/{id}` | 商品 | 商品详情（分类/品牌名 + SKU + 图集） | 公开 |
| `GET` | `/api/products/{productId}/reviews` | 商品评价 | 商品评价列表（公开，游客可看；带评分聚合） | 公开 |

⚠️ 白名单是**方法粒度**的：匿名 `POST` 打一条白名单里的 `GET` 路径得到的是 **401**
（Security 过滤器链先于 MVC 路由），带 token 才会走到 MVC 拿到 **405**。

## 二、管理端端点（`/api/admin/**`，全部走权限码）

| 方法 | 路径 | Tag | 说明 | 鉴权 |
|---|---|---|---|---|
| `GET` | `/api/admin/admins` | 管理端-管理员账号 | 管理员分页（含已禁用，keyword 匹配 username/nickname） | `admin:list` |
| `POST` | `/api/admin/admins` | 管理端-管理员账号 | 新建管理员（密码走 BCrypt 编码；用户名重复返回 400） | `admin:create` |
| `DELETE` | `/api/admin/admins/{id}` | 管理端-管理员账号 | 删除管理员（物理删，含清理角色关联；不许删自己） | `admin:delete` |
| `GET` | `/api/admin/admins/{id}` | 管理端-管理员账号 | 管理员详情（含角色 id 与角色码；不含 password） | `admin:detail` |
| `PUT` | `/api/admin/admins/{id}` | 管理端-管理员账号 | 编辑管理员（昵称/状态；不许停用自己） | `admin:update` |
| `PUT` | `/api/admin/admins/{id}/roles` | 管理端-管理员账号 | 给管理员分配角色（全量替换；不许清空自己的角色） | `admin:assign-role` |
| `GET` | `/api/admin/brands` | 管理端-品牌 | 品牌字典（管理端，含停用品牌，需 brand:list） | `brand:list` |
| `POST` | `/api/admin/brands` | 管理端-品牌 | 新增品牌（需 brand:create） | `brand:create` |
| `DELETE` | `/api/admin/brands/{id}` | 管理端-品牌 | 删除品牌（需 brand:delete，物理删 + 判商品引用） | `brand:delete` |
| `PUT` | `/api/admin/brands/{id}` | 管理端-品牌 | 修改品牌（需 brand:update，局部更新语义） | `brand:update` |
| `POST` | `/api/admin/categories` | 管理端-分类 | 新增分类（需 category:create） | `category:create` |
| `GET` | `/api/admin/categories/tree` | 管理端-分类 | 分类树（管理端，含二级子分类） | `category:list` |
| `DELETE` | `/api/admin/categories/{id}` | 管理端-分类 | 删除分类（需 category:delete，物理删 + 三重校验） | `category:delete` |
| `PUT` | `/api/admin/categories/{id}` | 管理端-分类 | 修改分类（需 category:update，局部更新语义） | `category:update` |
| `GET` | `/api/admin/coupons` | 管理端-优惠券 | 优惠券列表（需 coupon:list；status 不传则含下架券） | `coupon:list` |
| `POST` | `/api/admin/coupons` | 管理端-优惠券 | 新建优惠券（需 coupon:create） | `coupon:create` |
| `DELETE` | `/api/admin/coupons/{id}` | 管理端-优惠券 | 删除优惠券（需 coupon:delete；已被领取过的券删不掉） | `coupon:delete` |
| `GET` | `/api/admin/dashboard/overview` | 管理端-仪表盘 | 仪表盘概览（用户数/商品数/订单数/销售额；销售额为支付流水口径） | `dashboard:overview` |
| `GET` | `/api/admin/dashboard/trend` | 管理端-仪表盘 | 按天趋势（订单量 + 销售额，缺数据的日子补 0） | `dashboard:trend` |
| `GET` | `/api/admin/inventory/logs` | 管理端-库存 | 管理端库存流水（分页，可按 skuId / type 过滤；需 inventory:log 权限） | `inventory:log` |
| `GET` | `/api/admin/inventory/skus` | 管理端-库存 | 管理端库存列表（分页，需 inventory:list 权限） | `inventory:list` |
| `POST` | `/api/admin/inventory/skus/{skuId}/adjust` | 管理端-库存 | 调整库存（delta 带符号：正=补货，负=报损；需 inventory:adjust 权限） | `inventory:adjust` |
| `GET` | `/api/admin/orders` | 管理端-订单 | 管理端订单列表（全站分页，需 order:list 权限） | `order:list` |
| `GET` | `/api/admin/orders/{id}` | 管理端-订单 | 管理端订单详情（任意订单，需 order:detail 权限） | `order:detail` |
| `POST` | `/api/admin/orders/{id}/cancel` | 管理端-订单 | 管理端取消订单（仅待支付，需 order:cancel 权限） | `order:cancel` |
| `GET` | `/api/admin/permissions` | 管理端-权限字典 | 权限字典（不分页；给角色分配权限时用于渲染勾选框） | `permission:list` |
| `GET` | `/api/admin/products` | 管理端-商品 | 商品分页（管理端：含下架，status 可选过滤） | `product:list` |
| `POST` | `/api/admin/products` | 管理端-商品 | 新增商品（需 product:create） | `product:create` |
| `DELETE` | `/api/admin/products/{id}` | 管理端-商品 | 删除商品（软删主表） | `product:delete` |
| `GET` | `/api/admin/products/{id}` | 管理端-商品 | 商品详情（管理端：下架商品也能看） | `product:detail` |
| `PUT` | `/api/admin/products/{id}` | 管理端-商品 | 修改商品（含上下架：{"status":0} 即下架） | `product:update` |
| `GET` | `/api/admin/roles` | 管理端-角色 | 角色分页（含已停用，keyword 匹配 name/code） | `role:list` |
| `POST` | `/api/admin/roles` | 管理端-角色 | 新建角色（code 重复返回 400） | `role:create` |
| `DELETE` | `/api/admin/roles/{id}` | 管理端-角色 | 删除角色（含清理权限与账号关联；不许删 SUPER_ADMIN） | `role:delete` |
| `GET` | `/api/admin/roles/{id}` | 管理端-角色 | 角色详情（含权限 id 与权限码） | `role:detail` |
| `PUT` | `/api/admin/roles/{id}` | 管理端-角色 | 编辑角色（名称/说明/状态；不许停用 SUPER_ADMIN） | `role:update` |
| `PUT` | `/api/admin/roles/{id}/permissions` | 管理端-角色 | 给角色分配权限（全量替换；SUPER_ADMIN 只许增不许减） | `role:assign-permission` |
| `GET` | `/api/admin/users` | 管理端-用户 | 用户分页（管理端：含已禁用，keyword 匹配 username/nickname/phone） | `user:list` |
| `GET` | `/api/admin/users/{id}` | 管理端-用户 | 用户详情（管理端：已禁用的也能看） | `user:detail` |
| `PUT` | `/api/admin/users/{id}/status` | 管理端-用户 | 改用户状态（1=启用 0=禁用） | `user:status` |

### 权限码清单（本文档实际引用到的）

| 权限码 | 端点 |
|---|---|
| `admin:assign-role` | `PUT /api/admin/admins/{id}/roles` |
| `admin:create` | `POST /api/admin/admins` |
| `admin:delete` | `DELETE /api/admin/admins/{id}` |
| `admin:detail` | `GET /api/admin/admins/{id}` |
| `admin:list` | `GET /api/admin/admins` |
| `admin:update` | `PUT /api/admin/admins/{id}` |
| `brand:create` | `POST /api/admin/brands` |
| `brand:delete` | `DELETE /api/admin/brands/{id}` |
| `brand:list` | `GET /api/admin/brands` |
| `brand:update` | `PUT /api/admin/brands/{id}` |
| `category:create` | `POST /api/admin/categories` |
| `category:delete` | `DELETE /api/admin/categories/{id}` |
| `category:list` | `GET /api/admin/categories/tree` |
| `category:update` | `PUT /api/admin/categories/{id}` |
| `coupon:create` | `POST /api/admin/coupons` |
| `coupon:delete` | `DELETE /api/admin/coupons/{id}` |
| `coupon:list` | `GET /api/admin/coupons` |
| `dashboard:overview` | `GET /api/admin/dashboard/overview` |
| `dashboard:trend` | `GET /api/admin/dashboard/trend` |
| `inventory:adjust` | `POST /api/admin/inventory/skus/{skuId}/adjust` |
| `inventory:list` | `GET /api/admin/inventory/skus` |
| `inventory:log` | `GET /api/admin/inventory/logs` |
| `order:cancel` | `POST /api/admin/orders/{id}/cancel` |
| `order:detail` | `GET /api/admin/orders/{id}` |
| `order:list` | `GET /api/admin/orders` |
| `order:ship` | `POST /api/orders/{id}/ship` |
| `permission:list` | `GET /api/admin/permissions` |
| `product:create` | `POST /api/admin/products` |
| `product:delete` | `DELETE /api/admin/products/{id}` |
| `product:detail` | `GET /api/admin/products/{id}` |
| `product:list` | `GET /api/admin/products` |
| `product:update` | `PUT /api/admin/products/{id}` |
| `role:assign-permission` | `PUT /api/admin/roles/{id}/permissions` |
| `role:create` | `POST /api/admin/roles` |
| `role:delete` | `DELETE /api/admin/roles/{id}` |
| `role:detail` | `GET /api/admin/roles/{id}` |
| `role:list` | `GET /api/admin/roles` |
| `role:update` | `PUT /api/admin/roles/{id}` |
| `user:detail` | `GET /api/admin/users/{id}` |
| `user:list` | `GET /api/admin/users` |
| `user:status` | `PUT /api/admin/users/{id}/status` |

## 三、C 端端点（需登录）

| 方法 | 路径 | Tag | 说明 | 鉴权 |
|---|---|---|---|---|
| `GET` | `/api/addresses` | 收货地址 | 我的地址列表（默认地址排最前） | 登录 |
| `POST` | `/api/addresses` | 收货地址 | 新增地址（第一条自动成为默认） | 登录 |
| `DELETE` | `/api/addresses/{id}` | 收货地址 | 删除地址（删掉默认地址会自动补位；非本人返 404） | 登录 |
| `GET` | `/api/addresses/{id}` | 收货地址 | 地址详情（非本人返 404） | 登录 |
| `PUT` | `/api/addresses/{id}` | 收货地址 | 修改地址（业务字段全量覆盖；isDefault=true 表示设为默认） | 登录 |
| `PUT` | `/api/addresses/{id}/default` | 收货地址 | 设为默认地址（无 body；非本人返 404） | 登录 |
| `GET` | `/api/cart` | 购物车 | 购物车列表（实时价/库存/失效标记/小计） | 登录 |
| `POST` | `/api/cart` | 购物车 | 加入购物车（同 SKU 自动合并数量） | 登录 |
| `DELETE` | `/api/cart/{id}` | 购物车 | 删除购物车项（物理删除；非本人项返 404） | 登录 |
| `PUT` | `/api/cart/{id}` | 购物车 | 修改购物车项数量（不可超实时库存；非本人项返 404） | 登录 |
| `PUT` | `/api/cart/{id}/selected` | 购物车 | 勾选 / 取消勾选购物车项（非本人项返 404） | 登录 |
| `GET` | `/api/coupons/my` | 优惠券 | 我的优惠券（分页，含是否过期；size 上限 100） | 登录 |
| `POST` | `/api/coupons/{couponId}/receive` | 优惠券 | 领取优惠券（限量，抢完为止；同一张券每人限领一张） | 登录 |
| `GET` | `/api/db-check` | hello-controller |  | 登录 |
| `GET` | `/api/orders` | 订单 | 我的订单列表（分页，size 上限 100） | 登录 |
| `POST` | `/api/orders` | 订单 | 从购物车下单（结算已勾选的商品，返回订单 id） | 登录 |
| `GET` | `/api/orders/{id}` | 订单 | 订单详情（非本人订单返回 404） | 登录 |
| `POST` | `/api/orders/{id}/cancel` | 订单 | 取消订单（仅待支付可取消；非本人订单返回 404） | 登录 |
| `POST` | `/api/orders/{id}/confirm` | 订单 | 确认收货（仅已发货订单可确认；非本人订单返回 404） | 登录 |
| `POST` | `/api/orders/{id}/ship` | 订单 | 发货（管理端，需 order:ship 权限；仅已支付订单可发货） | `order:ship` |
| `GET` | `/api/payments` | 支付 | 我的支付记录（分页，size 上限 100；只返回本人订单的支付记录） | 登录 |
| `POST` | `/api/payments` | 支付 | 支付订单（同一订单只能成功支付一次；重复支付返回 400） | 登录 |
| `GET` | `/api/payments/{id}` | 支付 | 支付记录详情（非本人记录返回 404） | 登录 |
| `POST` | `/api/reviews` | 商品评价 | 发表评价（只能评自己的、已完成的订单明细；一条明细只能评一次） | 登录 |
| `GET` | `/api/reviews/my` | 商品评价 | 我的评价（分页，size 上限 100） | 登录 |
| `GET` | `/api/users/me` | 用户 | 我的资料（只能看自己） | 登录 |
| `PUT` | `/api/users/me/nickname` | 用户 | 改我的昵称 | 登录 |

## 四、按 Tag 分组（与 Swagger UI 的分组一致）

### hello-controller（1）

| 方法 | 路径 | Tag | 说明 | 鉴权 |
|---|---|---|---|---|
| `GET` | `/api/db-check` | hello-controller |  | 登录 |

### 优惠券（2）

| 方法 | 路径 | Tag | 说明 | 鉴权 |
|---|---|---|---|---|
| `GET` | `/api/coupons/my` | 优惠券 | 我的优惠券（分页，含是否过期；size 上限 100） | 登录 |
| `POST` | `/api/coupons/{couponId}/receive` | 优惠券 | 领取优惠券（限量，抢完为止；同一张券每人限领一张） | 登录 |

### 商品评价（2）

| 方法 | 路径 | Tag | 说明 | 鉴权 |
|---|---|---|---|---|
| `POST` | `/api/reviews` | 商品评价 | 发表评价（只能评自己的、已完成的订单明细；一条明细只能评一次） | 登录 |
| `GET` | `/api/reviews/my` | 商品评价 | 我的评价（分页，size 上限 100） | 登录 |

### 支付（3）

| 方法 | 路径 | Tag | 说明 | 鉴权 |
|---|---|---|---|---|
| `GET` | `/api/payments` | 支付 | 我的支付记录（分页，size 上限 100；只返回本人订单的支付记录） | 登录 |
| `POST` | `/api/payments` | 支付 | 支付订单（同一订单只能成功支付一次；重复支付返回 400） | 登录 |
| `GET` | `/api/payments/{id}` | 支付 | 支付记录详情（非本人记录返回 404） | 登录 |

### 收货地址（6）

| 方法 | 路径 | Tag | 说明 | 鉴权 |
|---|---|---|---|---|
| `GET` | `/api/addresses` | 收货地址 | 我的地址列表（默认地址排最前） | 登录 |
| `POST` | `/api/addresses` | 收货地址 | 新增地址（第一条自动成为默认） | 登录 |
| `DELETE` | `/api/addresses/{id}` | 收货地址 | 删除地址（删掉默认地址会自动补位；非本人返 404） | 登录 |
| `GET` | `/api/addresses/{id}` | 收货地址 | 地址详情（非本人返 404） | 登录 |
| `PUT` | `/api/addresses/{id}` | 收货地址 | 修改地址（业务字段全量覆盖；isDefault=true 表示设为默认） | 登录 |
| `PUT` | `/api/addresses/{id}/default` | 收货地址 | 设为默认地址（无 body；非本人返 404） | 登录 |

### 用户（2）

| 方法 | 路径 | Tag | 说明 | 鉴权 |
|---|---|---|---|---|
| `GET` | `/api/users/me` | 用户 | 我的资料（只能看自己） | 登录 |
| `PUT` | `/api/users/me/nickname` | 用户 | 改我的昵称 | 登录 |

### 管理端-仪表盘（2）

| 方法 | 路径 | Tag | 说明 | 鉴权 |
|---|---|---|---|---|
| `GET` | `/api/admin/dashboard/overview` | 管理端-仪表盘 | 仪表盘概览（用户数/商品数/订单数/销售额；销售额为支付流水口径） | `dashboard:overview` |
| `GET` | `/api/admin/dashboard/trend` | 管理端-仪表盘 | 按天趋势（订单量 + 销售额，缺数据的日子补 0） | `dashboard:trend` |

### 管理端-优惠券（3）

| 方法 | 路径 | Tag | 说明 | 鉴权 |
|---|---|---|---|---|
| `GET` | `/api/admin/coupons` | 管理端-优惠券 | 优惠券列表（需 coupon:list；status 不传则含下架券） | `coupon:list` |
| `POST` | `/api/admin/coupons` | 管理端-优惠券 | 新建优惠券（需 coupon:create） | `coupon:create` |
| `DELETE` | `/api/admin/coupons/{id}` | 管理端-优惠券 | 删除优惠券（需 coupon:delete；已被领取过的券删不掉） | `coupon:delete` |

### 管理端-分类（4）

| 方法 | 路径 | Tag | 说明 | 鉴权 |
|---|---|---|---|---|
| `POST` | `/api/admin/categories` | 管理端-分类 | 新增分类（需 category:create） | `category:create` |
| `GET` | `/api/admin/categories/tree` | 管理端-分类 | 分类树（管理端，含二级子分类） | `category:list` |
| `DELETE` | `/api/admin/categories/{id}` | 管理端-分类 | 删除分类（需 category:delete，物理删 + 三重校验） | `category:delete` |
| `PUT` | `/api/admin/categories/{id}` | 管理端-分类 | 修改分类（需 category:update，局部更新语义） | `category:update` |

### 管理端-品牌（4）

| 方法 | 路径 | Tag | 说明 | 鉴权 |
|---|---|---|---|---|
| `GET` | `/api/admin/brands` | 管理端-品牌 | 品牌字典（管理端，含停用品牌，需 brand:list） | `brand:list` |
| `POST` | `/api/admin/brands` | 管理端-品牌 | 新增品牌（需 brand:create） | `brand:create` |
| `DELETE` | `/api/admin/brands/{id}` | 管理端-品牌 | 删除品牌（需 brand:delete，物理删 + 判商品引用） | `brand:delete` |
| `PUT` | `/api/admin/brands/{id}` | 管理端-品牌 | 修改品牌（需 brand:update，局部更新语义） | `brand:update` |

### 管理端-商品（5）

| 方法 | 路径 | Tag | 说明 | 鉴权 |
|---|---|---|---|---|
| `GET` | `/api/admin/products` | 管理端-商品 | 商品分页（管理端：含下架，status 可选过滤） | `product:list` |
| `POST` | `/api/admin/products` | 管理端-商品 | 新增商品（需 product:create） | `product:create` |
| `DELETE` | `/api/admin/products/{id}` | 管理端-商品 | 删除商品（软删主表） | `product:delete` |
| `GET` | `/api/admin/products/{id}` | 管理端-商品 | 商品详情（管理端：下架商品也能看） | `product:detail` |
| `PUT` | `/api/admin/products/{id}` | 管理端-商品 | 修改商品（含上下架：{"status":0} 即下架） | `product:update` |

### 管理端-库存（3）

| 方法 | 路径 | Tag | 说明 | 鉴权 |
|---|---|---|---|---|
| `GET` | `/api/admin/inventory/logs` | 管理端-库存 | 管理端库存流水（分页，可按 skuId / type 过滤；需 inventory:log 权限） | `inventory:log` |
| `GET` | `/api/admin/inventory/skus` | 管理端-库存 | 管理端库存列表（分页，需 inventory:list 权限） | `inventory:list` |
| `POST` | `/api/admin/inventory/skus/{skuId}/adjust` | 管理端-库存 | 调整库存（delta 带符号：正=补货，负=报损；需 inventory:adjust 权限） | `inventory:adjust` |

### 管理端-权限字典（1）

| 方法 | 路径 | Tag | 说明 | 鉴权 |
|---|---|---|---|---|
| `GET` | `/api/admin/permissions` | 管理端-权限字典 | 权限字典（不分页；给角色分配权限时用于渲染勾选框） | `permission:list` |

### 管理端-用户（3）

| 方法 | 路径 | Tag | 说明 | 鉴权 |
|---|---|---|---|---|
| `GET` | `/api/admin/users` | 管理端-用户 | 用户分页（管理端：含已禁用，keyword 匹配 username/nickname/phone） | `user:list` |
| `GET` | `/api/admin/users/{id}` | 管理端-用户 | 用户详情（管理端：已禁用的也能看） | `user:detail` |
| `PUT` | `/api/admin/users/{id}/status` | 管理端-用户 | 改用户状态（1=启用 0=禁用） | `user:status` |

### 管理端-管理员账号（6）

| 方法 | 路径 | Tag | 说明 | 鉴权 |
|---|---|---|---|---|
| `GET` | `/api/admin/admins` | 管理端-管理员账号 | 管理员分页（含已禁用，keyword 匹配 username/nickname） | `admin:list` |
| `POST` | `/api/admin/admins` | 管理端-管理员账号 | 新建管理员（密码走 BCrypt 编码；用户名重复返回 400） | `admin:create` |
| `DELETE` | `/api/admin/admins/{id}` | 管理端-管理员账号 | 删除管理员（物理删，含清理角色关联；不许删自己） | `admin:delete` |
| `GET` | `/api/admin/admins/{id}` | 管理端-管理员账号 | 管理员详情（含角色 id 与角色码；不含 password） | `admin:detail` |
| `PUT` | `/api/admin/admins/{id}` | 管理端-管理员账号 | 编辑管理员（昵称/状态；不许停用自己） | `admin:update` |
| `PUT` | `/api/admin/admins/{id}/roles` | 管理端-管理员账号 | 给管理员分配角色（全量替换；不许清空自己的角色） | `admin:assign-role` |

### 管理端-角色（6）

| 方法 | 路径 | Tag | 说明 | 鉴权 |
|---|---|---|---|---|
| `GET` | `/api/admin/roles` | 管理端-角色 | 角色分页（含已停用，keyword 匹配 name/code） | `role:list` |
| `POST` | `/api/admin/roles` | 管理端-角色 | 新建角色（code 重复返回 400） | `role:create` |
| `DELETE` | `/api/admin/roles/{id}` | 管理端-角色 | 删除角色（含清理权限与账号关联；不许删 SUPER_ADMIN） | `role:delete` |
| `GET` | `/api/admin/roles/{id}` | 管理端-角色 | 角色详情（含权限 id 与权限码） | `role:detail` |
| `PUT` | `/api/admin/roles/{id}` | 管理端-角色 | 编辑角色（名称/说明/状态；不许停用 SUPER_ADMIN） | `role:update` |
| `PUT` | `/api/admin/roles/{id}/permissions` | 管理端-角色 | 给角色分配权限（全量替换；SUPER_ADMIN 只许增不许减） | `role:assign-permission` |

### 管理端-订单（3）

| 方法 | 路径 | Tag | 说明 | 鉴权 |
|---|---|---|---|---|
| `GET` | `/api/admin/orders` | 管理端-订单 | 管理端订单列表（全站分页，需 order:list 权限） | `order:list` |
| `GET` | `/api/admin/orders/{id}` | 管理端-订单 | 管理端订单详情（任意订单，需 order:detail 权限） | `order:detail` |
| `POST` | `/api/admin/orders/{id}/cancel` | 管理端-订单 | 管理端取消订单（仅待支付，需 order:cancel 权限） | `order:cancel` |

### 订单（6）

| 方法 | 路径 | Tag | 说明 | 鉴权 |
|---|---|---|---|---|
| `GET` | `/api/orders` | 订单 | 我的订单列表（分页，size 上限 100） | 登录 |
| `POST` | `/api/orders` | 订单 | 从购物车下单（结算已勾选的商品，返回订单 id） | 登录 |
| `GET` | `/api/orders/{id}` | 订单 | 订单详情（非本人订单返回 404） | 登录 |
| `POST` | `/api/orders/{id}/cancel` | 订单 | 取消订单（仅待支付可取消；非本人订单返回 404） | 登录 |
| `POST` | `/api/orders/{id}/confirm` | 订单 | 确认收货（仅已发货订单可确认；非本人订单返回 404） | 登录 |
| `POST` | `/api/orders/{id}/ship` | 订单 | 发货（管理端，需 order:ship 权限；仅已支付订单可发货） | `order:ship` |

### 购物车（5）

| 方法 | 路径 | Tag | 说明 | 鉴权 |
|---|---|---|---|---|
| `GET` | `/api/cart` | 购物车 | 购物车列表（实时价/库存/失效标记/小计） | 登录 |
| `POST` | `/api/cart` | 购物车 | 加入购物车（同 SKU 自动合并数量） | 登录 |
| `DELETE` | `/api/cart/{id}` | 购物车 | 删除购物车项（物理删除；非本人项返 404） | 登录 |
| `PUT` | `/api/cart/{id}` | 购物车 | 修改购物车项数量（不可超实时库存；非本人项返 404） | 登录 |
| `PUT` | `/api/cart/{id}/selected` | 购物车 | 勾选 / 取消勾选购物车项（非本人项返 404） | 登录 |

## 五、口径偏离（已知、未修）

**带权限码、但不在 `/api/admin/**` 下的端点**：

| 方法 | 路径 | 权限码 | 出处 |
|---|---|---|---|
| `POST` | `/api/orders/{id}/ship` | `order:ship` | `mall-order/src/main/java/com/mallx/order/controller/OrderController.java` |

★ **这不是漏洞，是历史口径**：Day 15 设计发货接口时，管理端动作还没有
「一律走 `/api/admin/**`」的约定（那条约定是 Day 17/18 做数据权限反转时立的）。
它安全的原因是：`/api/orders/**` **不在任何白名单前缀里**，所以不存在
「白名单先匹配先赢 ⇒ `@PreAuthorize` 被跳过」这条唯一的静默公开路径。

⚠️ **不修的理由**：把它挪到 `/api/admin/orders/{id}/ship` 会让
`day15-ship-confirm.py`（M1 全链路的一环）立刻失效，属于「改已验证契约换一致性」，
收益只有命名整齐。⇒ 记在 `docs/backlog.md`，等真要统一管理端前缀时一起动。

