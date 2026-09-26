# Day 30 — 索引体检总表（30 个索引，逐个交代）

> 本日**没有改一行 Java、没有动一个 DDL、没有加/删一个索引**。
> Day 27 审了商品侧 13 条查询、Day 29 审了 Dashboard 5 条 —— 都是**按查询找索引**。
> 本日反过来：**按索引找查询**，把全库 **30 个索引**逐个交代一遍。
>
> 一句话结论：**30 个里 26 个有明确的服务对象；4 个没有；其中只有 3 个值得动** ——
> 而且「值得动」的判据不是「有没有被用上」，是**「它的写入成本是不是白付」**。

---

## 一、方法与取证口径（★ 先说清证据等级）

本日**主要是代码取证**，不是实测。三类证据必须分清，混在一起就会得出假结论：

| 等级 | 含义 | 本日覆盖 |
|---|---|---|
| **A · 实测** | 临时库 + 3 万行 + `EXPLAIN (ANALYZE)` 确认计划里出现了该索引 | `day27`（13 条查询）+ `day29`（5 条） |
| **B · 代码引用取证** | `grep` 到明确使用该列的查询（给出 `文件:行`） | 本日新增，覆盖全部 30 个 |
| **C · 无调用方** | 全仓（`.java` / `*.xml` / `*.sql`，排除 `target/` 与 `.idea/`）**搜不到任何使用该列的查询** | 本日新增 |

★ **B 与 C 都不等于 A。**「有调用方」不等于「被用上」（`status` 就是反例：
有 3 条查询按它过滤，但它选择性太低，计划器从来不选它）；
「搜不到调用方」也不等于「永远没用」（V2.0 的功能会用到）。
**所以下面每一行都标了等级，不含糊。**

---

## 二、总表

### 2.1 商品域

| 索引 | 服务于哪条查询 | 等级 | 结论 |
|---|---|---|---|
| `idx_products_category_id` | `countByCategoryId` / C 端列表按分类 | **A** | ⚠️ 仅**不带 LIMIT** 时生效（列表走 PK 反向扫） |
| `idx_products_brand_id` | `ProductMapper.xml:41` `countByBrandId` | B | ✅ 有效（仅 count 场景） |
| `idx_products_status` | — 无查询按 `status` 单独过滤到值得走索引 | **A** | ❌ **死索引**（`status=1` 命中 99%，day27 Q1 实测从不被选中） |
| `idx_products_is_deleted` | `countProducts`（Dashboard） | **A** | ✅ 有效（day29 D2 实测用上） |
| `idx_products_search` | 搜索全文 | **A** | ⚠️ 有效但**生产形状用不上**（被 `OR` 挡住，Day 28 方案） |
| `idx_products_name_trgm` | 搜索单列 ILIKE | **A** | ✅ 有效（多列 OR 时失效） |
| `idx_product_skus_product_id` | 商品详情装配 / 搜索 EXISTS | **A** | ✅ 有效（day27 Q8a 实测） |
| `idx_product_skus_is_deleted` | — 无 `count(*) FROM product_skus WHERE is_deleted=0` | **C** | ❌ **无调用方** |
| `idx_product_skus_attributes` | 属性筛选 `attributes @>` | **A** | ✅ 有效（JSONB GIN） |
| `idx_product_images_product_id` | 商品详情装配图集 | B | ✅ 有效（未实测） |

### 2.2 交易域

| 索引 | 服务于哪条查询 | 等级 | 结论 |
|---|---|---|---|
| `idx_orders_user_id` | 我的订单列表 | **A** | ✅ 有效 |
| `idx_orders_status` | 超时关单扫描（每 60s）/ `countOrders` | **A** | ✅ 有效 |
| `idx_orders_created_at` | `selectDailyTrend` 日期过滤 | **A** | ✅ 有效 |
| `idx_order_items_order_id` | 订单详情取明细 | **A** | ✅ 有效 |
| `idx_order_items_sku_id` | — `sku_id` 只出现在 **SELECT 列**，没有 `WHERE sku_id =` | **C** | ❌ **无调用方** |
| `idx_payments_order_id` | `PaymentMapper` 的 `INNER JOIN orders o ON o.id = p.order_id` | B | ✅ 有效（JOIN 探针；无 `WHERE order_id =`） |
| `idx_inventory_logs_sku_id` | 管理端流水页按 sku 倒序 | **A** | ✅ 有效 |

### 2.3 用户 / 购物车 / 评价

| 索引 | 服务于哪条查询 | 等级 | 结论 |
|---|---|---|---|
| `idx_user_addresses_user_id` | `AddressServiceImpl` ×4 `.eq(getUserId)` | B | ✅ 有效 |
| `uk_user_addresses_default` | **不是性能索引** —— 把「每用户最多一条默认地址」下推到 DB | — | ✅ 业务约束，保留 |
| `idx_cart_items_user_id` | `CartItemMapper.xml:42` 购物车列表 | B | ✅ 有效 |
| `idx_cart_items_sku_id` | `CartServiceImpl:44` `.eq(getSkuId)` 加购查重 | B | ✅ 有效 |
| `idx_reviews_product_id` | 商品详情页评价列表 | **A** | ✅ 有效 |
| `idx_reviews_user_id` | `ReviewMapper.xml:91 WHERE r.user_id = ?`（`GET /api/reviews/my`） | B | ✅ 有效 |

### 2.4 营销 / RBAC / 售后

| 索引 | 服务于哪条查询 | 等级 | 结论 |
|---|---|---|---|
| `idx_user_coupons_user_id` | `UserCouponMapper` ×5（我的券 / 核销 / 退券） | **A**（Day 33 实测） | ❌ **冗余** —— 被 `uk_user_coupons_user_coupon`（09 号补丁的 `UNIQUE(user_id, coupon_id)`）**完全覆盖**，实测**从未被用上** |
| `idx_user_coupons_coupon_id` | `CouponServiceImpl:250` 券删除前的引用校验 | **A**（Day 33 对照实测） | ✅ 有效（DROP 后退化成全表扫：1.60 → 7.80 ms） |
| `idx_coupons_status` | `CouponMapper:43/62/73` `status = 1` + `CouponServiceImpl:113` | **A**（Day 33 实测） | ❌ **死索引** —— `status=1` 命中 95%，计划器改用 PK 反向扫（与 `idx_products_status` 同类） |
| `idx_admin_roles_role_id` | `AdminRbacMapper:43/60/67 WHERE role_id = ?` | B | ✅ 有效 |
| `idx_role_permissions_permission_id` | — 唯一查询按 `role_id` 过滤 | **C** | ❌ **冗余** —— 见 §三.2 |
| `idx_after_sales_order_id` | — `after_sales` 表**零 Java/XML 引用** | **C** | ❌ 无调用方（V2.0 才会用） |
| `idx_after_sales_user_id` | 同上 | **C** | ❌ 无调用方 |

**合计 30 个**（★ 下表已按 Day 31 / Day 33 的实测订正）：

| 结论 | 数量 | 说明 |
|---|---|---|
| ✅ **实测确认有效**（A 级） | **11** | 含 Day 33 对照实测的 `idx_user_coupons_coupon_id` |
| ⚠️ 有效但有条件（A 级） | 2 | `idx_products_category_id`（仅无 LIMIT 时）、`idx_products_search`（生产形状被 OR 挡住） |
| ✅ 代码取证有效（**B 级**，未经实测） | 8 | ★ Day 33 已证明 **B 级不足以判「有效」**，见 §三.4 |
| ❌ 死 / 无调用方 / 冗余 | **8** | `idx_products_status` · `idx_product_skus_is_deleted` · `idx_order_items_sku_id` · `idx_user_coupons_user_id` · `idx_coupons_status` · `idx_role_permissions_permission_id` · `idx_after_sales_order_id` · `idx_after_sales_user_id` |
| ✅ 业务约束（非性能索引） | 1 | `uk_user_addresses_default` |

---

## 三、★ 值得处理的，以及为什么只有 3 个

### 3.1 判据不是「有没有被用上」，是「写入成本是不是白付」

一个索引的**成本**是「每次 INSERT/UPDATE/DELETE 都要维护它」，**收益**是「某条查询快多少」。
所以要不要删，看的是**这张表有多大、写多频繁** —— 而不是「它有没有被用上」：

| 候选 | 表规模 | 写入频率 | 值得动吗 |
|---|---|---|---|
| `idx_products_status` | 3 万商品 | 商品增删改（低频） | ✅ **值得删** —— 大表 + 从被选中过 0 次 |
| `idx_order_items_sku_id` | 3 万明细 | **每张订单必写多行**（高频） | ✅ **值得删** —— 高频写入且零调用方 |
| `idx_product_skus_is_deleted` | 6 万 SKU | 商品写必带 SKU 写 | ✅ **值得删** —— 同上 |
| `idx_after_sales_order_id` / `_user_id` | **0 行**（表空） | 0 | ❌ **不值得动** —— **空表上的索引零成本**，删了 V2.0 还得加回来，纯churn |
| `idx_role_permissions_permission_id` | ~100 行 | 权限变更（极低频） | ⚠️ 可留可删 —— 收益微小，删了也没坏处 |

★ **这一条是本日最值钱的**：如果按「有没有被用上」排序，
`idx_after_sales_*`（零调用方）会排在最前面 —— 而它们**恰恰是最不该动的**。
**空表上的索引不花钱。** 按「使用情况」排序会得到与「按成本」排序**相反**的结论。

### 3.2 `idx_role_permissions_permission_id` 是**冗余**，不是「没用」

`role_permissions` 的主键是 **`(role_id, permission_id)`**（`01-schema.sql:363`）——
PG 为此已经自动建了 `role_permissions_pkey`。而额外这个**单列** `permission_id` 索引：

- 唯一的引用是 `AdminRbacMapper.xml:41`：`SELECT permission_id ... WHERE role_id = ? ORDER BY permission_id`
  —— 过滤用 `role_id`（PK 第一列），排序在 `role_id` 固定后由 PK 顺序天然满足；
- 全仓**搜不到任何 `WHERE permission_id = ?`** 的查询。

⇒ 它被主键索引**完全覆盖**，属于**冗余索引**（多一份写入成本、多一份优化器候选）。
★ 一般化：**建索引前先看主键**。`(a, b)` 的 PK 已经能服务「按 a 查」和「按 a 查并按 b 排」。

### 3.3 `idx_coupons_status` —— ✅ **已由 Day 33 实测定性：死索引**

（原文写的是「不能按『有调用方』就判有效，必须实测」。**这个怀疑是对的。**）

Day 33 的 DROP 实验：把它删掉，C 端可领券列表的计划**逐字节不变** ——
`status = 1` 命中 95%，计划器改用 **PK 反向扫 + 过滤**（凑够 10 条就停）。
⇒ 与 `idx_products_status` **完全同类**。

### 3.4 ★★ Day 33 订正：**B 级证据不足以判「有效」**

本节原本判 `idx_user_coupons_user_id` = ✅ 有效，理由是「`UserCouponMapper` 有 5 处按 `user_id` 查」。
**Day 33 证明这个判断是错的**：那些查询实际由 `uk_user_coupons_user_coupon`
（09 号补丁的 `UNIQUE(user_id, coupon_id)`，**第一列就是 `user_id`**）服务，
单列索引**从头到尾没被用上过** ⇒ 它是**冗余**，不是有效。

⇒ **B 级（代码取证）只能得出「有调用方」，要判「有效」必须升到 A 级（EXPLAIN 实测）。**
   ★ 上表还剩 **8 个 B 级**条目，它们**都可能藏着同类问题** ——
   尤其是「可能被某个复合 / 唯一索引以它为前缀覆盖」的那几个。

---

## 四、★ 三条判据

1. ★★ **「有调用方」不等于「被用上」** —— 有 3 个反例（`idx_products_status` 有查询按它过滤、
   `payments(status)` 同理、`idx_coupons_status` 待定）。**只有 `EXPLAIN` 能证明「被用上」。**
2. ★★ **「没被用上」不等于「该删」** —— 要不要删看**写入成本**。
   空表 / 小表上的索引**不花钱**，删了只是 churn（`idx_after_sales_*` 就是这一类）。
   **按「使用情况」排序会得到与「按成本」排序相反的结论。**
3. ★ **建索引前先看主键** —— `(a, b)` 的 PK 已覆盖「按 a 查」，再建一个单列 `a` 索引是纯冗余。

---

## 五、下一步（★ 本日不改，留作决策）

1. **删 3 个索引**（`idx_products_status` / `idx_order_items_sku_id` / `idx_product_skus_is_deleted`）——
   写成新补丁 `backend/sql/15-drop-dead-indexes.sql`（`DROP INDEX IF EXISTS`，幂等）。
   ⚠️ **必须先实测确认它们真的没被选中**：目前只有 `idx_products_status` 有 day27 的实测，
   另两个是「无调用方」推断（等级 C）。**推断不是实测** —— 建议先补一轮 EXPLAIN。
   → ✅ **已由 Day 31 补测**：`docs/daily/Day-31-DROP实验-索引可删性验证.md` ——
   两个候选索引 **DROP 前后计划逐字节相同**，且**对照组**（DROP 两个确实在用的索引）计划都变了，
   证明装置有区分度 ⇒ **删除安全，证据已备齐**。
2. **实测 `idx_coupons_status`**（等级 B → A），判据同 Day 29 的 A/B 对照。
   → ✅ **已由 Day 33 完成**：`docs/daily/Day-33-券侧索引收尾.md` ——
   它是**死索引**；同批还测出 `idx_user_coupons_user_id` 是**冗余**
   （被 `UNIQUE(user_id, coupon_id)` 覆盖），并**订正了本表原本的「✅ 有效」判断**。
   ★ 删除候选因此从 3 个变成 **5 个**。
3. ★ **按 §3.4 补测剩余 8 个 B 级条目**（优先测「疑似被复合索引覆盖」的那几个）。
3. **把 `day27` / `day28` / `day29` 挂进 CI**（三个都是幂等 + 零副作用的临时库脚本）。
4. 实现 Day 28 的搜索修复（唯一有量级收益的一条，**29x**）。

---

## 六、复现本日的取证

```bash
# 全部索引定义（30 个）
grep -n "CREATE INDEX\|CREATE UNIQUE INDEX" backend/sql/*.sql

# 某个索引列有没有调用方（排除 IDE 缓存与构建产物）
cd backend && grep -rn "permission_id" --include="*.java" --include="*.xml" --include="*.sql" \
    mallx/ sql/ | grep -v "/target/" | grep -v "\.idea/"

# 主键（判断冗余时的关键输入）
grep -n -A6 "CREATE TABLE IF NOT EXISTS role_permissions" backend/sql/01-schema.sql
```

> ★ **本日踩到的一个取证陷阱**：第一次搜 `after_sales` 时命中了 `.idea/dataSources/*.xml`，
> 差点把「IDE 的数据库缓存」当成调用方。**取证必须排除 `target/` 与 `.idea/`**，
> 否则搜索结果是噪音 —— 反过来，也差点把 `idx_reviews_user_id` 误判成死索引
> （它其实被 `GET /api/reviews/my` 用着，写在 XML 第 91 行，我第一次没搜到）。
> **判「没有」比判「有」危险得多**：判错「有」只是多留一个索引，判错「没有」会删掉在用的东西。
