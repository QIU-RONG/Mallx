# Day 34 — 「被复合索引覆盖」扫尾（★ 并区分出**两种不同的冗余**）

> 本日**没有改一行 Java、没有动一个生产索引**。
> Day 33 发现 `idx_user_coupons_user_id` 被 `UNIQUE(user_id, coupon_id)` 覆盖之后，
> 本日把**同一个模式**在别处扫了一遍 —— 逐表核对约束形态，只剩 `cart_items` 符合。
>
> 一句话结论：**购物车两个索引都该删**（一个 A 型、一个 B 型），
> 并且**第一次把「冗余」拆成了两种**，因为它们的判据不一样。

---

## 一、扫的模式：谁的「第一列」被复合索引占了

| 表 | 约束 | 单列索引 | 结论 |
|---|---|---|---|
| `user_coupons` | `UNIQUE (user_id, coupon_id)`（09 号补丁） | `idx_user_coupons_user_id` | ❌ 冗余（Day 33 已证） |
| **`cart_items`** | **`UNIQUE (user_id, sku_id)`（建表就有）** | `idx_cart_items_user_id` | ❌ **冗余**（本日证） |
| `cart_items` | 同上 | `idx_cart_items_sku_id` | ❌ **冗余**（本日证，见 §三） |
| `admin_roles` | `PRIMARY KEY (admin_id, role_id)` | `idx_admin_roles_role_id` | ⚠️ `role_id` **不是前缀** ⇒ 理论上必要（**但实测计划器不用它，见 §四**） |
| `role_permissions` | `PRIMARY KEY (role_id, permission_id)` | `idx_role_permissions_permission_id` | ❌ 冗余（Day 30 已判） |

★ 判据：**建单列索引前先看主键 / 唯一约束的列顺序。**
`(a, b)` 的复合索引能服务「按 a 查」，**服务不了「按 b 查」** —— 所以要不要删，
看的是**这一列在复合索引里是不是前缀**，不是「有没有人查这一列」。

---

## 二、结果（21 / 21 passed）

| ID | 类型 | 索引 | DROP 后 | 结论 |
|---|---|---|---|---|
| C1 | **B 型** | `idx_cart_items_user_id` | 计划**变了**，但**仍走索引**（`uk_cart_user_sku`），0.73 → 0.67 ms | ❌ **冗余** |
| C2 | **A 型** | `idx_cart_items_sku_id` | 计划**完全不变** | ❌ **从来没被用上** |
| C3 | 对照 | `idx_products_category_id` | 计划**变了**（Day 27 已证它被用上） | ✅ 装置有区分度 |
| C4 | 探针 | `idx_admin_roles_role_id` | 203 行小表，`Seq Scan` | ⚠️ **表太小，不是索引没用**（§四） |

---

## 三、★★ 本日最值钱的发现：「冗余」有两种，判据不一样

Day 31 / 33 的判据是「**DROP 后计划逐字节不变 ⇒ 可删**」。
本日 C1 把这个判据**打穿了**：DROP 之后计划**变了**，但——

```
A（索引都在）: Index Scan using idx_cart_items_user_id
B（已 DROP） : Bitmap Index Scan on uk_cart_user_sku   ← 换了另一个索引，还是走索引
耗时          : 0.73 ms → 0.67 ms                       ← 没变
```

**它不是「没被用上」，而是「被用上了，但有替代品」。** 两者都该删，但现象完全不同：

| | **A 型**：从来没被用上 | **B 型**：有替代索引 |
|---|---|---|
| DROP 后计划 | **完全不变** | **会变**（换到替代索引） |
| DROP 后是否还走索引 | 是（本来就走的别的） | **是**（替代索引） |
| 是否退化 | 否 | 否（**耗时不变**） |
| 判据 | 计划不变 | **仍走索引 + 耗时不变** |
| 例子 | `idx_cart_items_sku_id`（本日）、`idx_user_coupons_user_id`、`idx_coupons_status` | **`idx_cart_items_user_id`**（本日） |

★ **第一版我把 C1 也按 A 型判**（「DROP 后计划必须不变」），于是它的 FAIL 被打印成
「该索引其实有用，不该删」——**那是判据太窄，不是索引不该删。**
⇒ 判据本身也需要按证据分类：**「计划不变」只是 A 型的判据，不能套到 B 型上。**

---

## 四、`idx_admin_roles_role_id`：我的假设被实测否掉了

我原本把它当**对照组**，理由是「`admin_roles` 的主键是 `(admin_id, role_id)`，
`role_id` 不是前缀 ⇒ 这个索引是必要的」。

实测：`admin_roles` **只有 203 行** ⇒ 计划器直接 `Seq Scan`，**根本不用它**。
⇒ 所以它做不了对照（对照必须「DROP 后计划会变」）。

★ 这不是「索引没用」，是**表太小** —— 与 Day 33 的 `coupons`（200 行）完全同类。
**若 admin 规模真涨起来，它会开始有用。**

⇒ 这一条同时暴露了一个操作层面的教训：
**对照组不能随便挑，它自己也得满足「规模够大、索引确实在用」这个前提。**
本日换用 `idx_products_category_id`（Day 27 已证会被用上、30 万行量级）才成立。

---

## 五、结论：删除候选从 5 个变成 **7 个**

| # | 索引 | 类型 | 证据 |
|---|---|---|---|
| 1 | `idx_products_status` | A | Day 27 实测 + Day 31 DROP |
| 2 | `idx_product_skus_is_deleted` | A | Day 31 DROP |
| 3 | `idx_order_items_sku_id` | A | 零调用方（grep） |
| 4 | `idx_coupons_status` | A | Day 33 DROP |
| 5 | `idx_user_coupons_user_id` | A | Day 33 DROP |
| 6 | **`idx_cart_items_user_id`** | **B** | Day 34 DROP（替代索引 `uk_cart_user_sku`） |
| 7 | **`idx_cart_items_sku_id`** | **A** | Day 34 DROP |

★ 仍然**不要动**的：`idx_after_sales_*`（表是空的，零成本）、
`idx_role_permissions_permission_id`（小表，可留可删）、`idx_admin_roles_role_id`（表太小，删了没意义）。

### 「被复合索引覆盖」这个模式已扫完

`user_coupons` / `cart_items` / `role_permissions` 三处都已定性。
**剩下 6 个 B 级条目**（`idx_products_brand_id` / `idx_product_images_product_id` /
`idx_payments_order_id` / `idx_user_addresses_user_id` / `idx_reviews_user_id`）
经约束核对**都不符合这个模式**：
- `idx_user_addresses_user_id`：`uk_user_addresses_default` 是**部分索引**（`WHERE is_default = true`）
  ⇒ 服务不了「列全部地址」的查询 ⇒ 这个单列索引**确实必要**；
- 其余四个所在表**没有任何以它们为前缀的复合/唯一约束**。

⇒ **不需要再测了。** 这条线可以收工。

---

## 六、复现

```bash
cd backend/loadtest
python day34-cart-index-probe.py     # 21/21
```
