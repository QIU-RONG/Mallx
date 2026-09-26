# Day 33 — 券侧索引收尾（★ 推翻了我自己在 Day 30 的一个结论）

> 本日**没有改一行 Java、没有动一个生产索引**。
> Day 30 的体检总表里只剩一个索引没定性（`idx_coupons_status`），本日把它测掉；
> 顺手发现**第二个**可疑项，而它**推翻了我 Day 30 判的「有效」**。
>
> 一句话结论：**两个索引都不该留** —— `idx_coupons_status` 是死索引；
> `idx_user_coupons_user_id` 是**冗余**（被 09 号补丁的 UNIQUE 索引完全覆盖）。

---

## 一、结果（19 / 19 passed）

沿用 Day 31 的 **DROP 实验**：把索引真删掉再跑，比计划变不变；同时留一个**对照组**。

| ID | 类型 | 被 DROP 的索引 | 计划变化 | A（索引都在）实际用上的 |
|---|---|---|---|---|
| S1 | **候选** | `idx_coupons_status` | **没变** ❌ | `coupons_pkey`（PK 反向扫） |
| S2 | **候选** | `idx_user_coupons_user_id` | **没变** ❌ | **`uk_user_coupons_user_coupon`** |
| S3 | **对照** | `idx_user_coupons_coupon_id` | **变了** ✅ | 该索引（1.60 ms → **7.80 ms**，退化成全表扫） |

对照组的 `1.60 ms → 7.80 ms` 证明**装置有区分度** ⇒ S1/S2 的「没变」不是装置失灵。

---

## 二、★★ 订正：`idx_user_coupons_user_id` 不是「有效」，是**冗余**

**Day 30 我把它判成 ✅ 有效**，理由是「`UserCouponMapper` 有 5 处按 `user_id` 查」。
**这个判断是错的** —— 它有调用方，但那些调用方**由另一个索引服务**：

09 号补丁给 `user_coupons` 加了 `UNIQUE (user_id, coupon_id)`
（为了防「同一用户重复领同一张券」），PG 为此建了唯一索引 `uk_user_coupons_user_coupon`。
**它的第一列就是 `user_id`** ⇒ 「按 user_id 查」它完全能服务，而且**实测就是它在服务**。

计划实证（阶段 A 的 S2）：

```
Index Scan using uk_user_coupons_user_coupon on user_coupons
    Index Cond: (user_id = ...)
```

⇒ 单列的 `idx_user_coupons_user_id` **从头到尾没被用上过**，纯属多一份写入成本。

★ 这与 `idx_role_permissions_permission_id`（Day 30）**是同一类问题**：
**建单列索引前先看有没有以该列为前缀的复合/唯一索引。**

### 2.1 这一条最值得记的地方

「**有调用方**」这个证据等级（Day 30 的 **B 级**）**本身就不足以判「有效」** ——
它只能证明「有人查这一列」，不能证明「计划器会选这个索引」。
本日是我**第二次**踩这条（第一次是 Day 29 的 `payments(status)`），
而且这次是**我自己写下的结论被自己推翻**。

⇒ 判据升级：**B 级证据只能得出「有调用方」，要判「有效」必须升到 A 级（EXPLAIN 实测）。**
   Day 30 表里还剩 **8 个 B 级**条目，它们**都可能藏着同类问题**（§五 列为待办）。

---

## 三、`idx_coupons_status`：死索引（与 `idx_products_status` 同类）

C 端可领券列表的真实 SQL（`CouponMapper.xml:73` 一带）：

```sql
SELECT ... FROM coupons
 WHERE status = 1
   AND start_time <= CURRENT_TIMESTAMP
   AND end_time   >= CURRENT_TIMESTAMP
   AND received_count < total_count
 ORDER BY id DESC LIMIT 10
```

`status = 1` 命中 **95%** 的行（低选择性，与 `idx_products_status` 一模一样），
而 `ORDER BY id DESC` 让计划器改用 **PK 反向扫 + 过滤**（凑够 10 条就停）。
⇒ `idx_coupons_status` **从不被选中**，DROP 前后计划逐字节相同。

---

## 四、★ 本日新增的一个做法：**两个规模都要报**

`coupons` 是张**小表** —— 真实业务里几十到几百行。
所以在 2 万行上测出的「索引有没有用」，**技术上正确、业务上无意义**。

本日把两个规模都测了：

| coupons 规模 | S1 耗时 | 计划 |
|---|---|---|
| 20,000 行（压力） | 0.28 ms | `coupons_pkey` 反向扫 |
| **200 行（真实）** | **0.42 ms** | `Seq Scan on coupons` |

★ 200 行时**直接全表扫**，0.42 ms —— 索引的有无**完全不重要**。

⇒ 判据：**样本既不能太小（测不出索引），也不能脱离业务现实（结论没意义）——两个规模都要看。**
   这与 Day 32 的「偏斜分布」是同一枚硬币的两面：
   Day 32 是「样本太平均会测不出问题」，本日是「样本太大也会得出无意义的结论」。

---

## 五、结论与下一步

### 5.1 券侧两个索引：都不该留

| 索引 | 定性 | 建议 |
|---|---|---|
| `idx_coupons_status` | ❌ 死索引（95% 选择性） | 可删 —— 但**表小，收益也小** |
| `idx_user_coupons_user_id` | ❌ **冗余**（被 `uk_user_coupons_user_coupon` 覆盖） | **可删** —— 写入成本白付 |

### 5.2 ★ 一个更大的待办：Day 30 表里还有 8 个 **B 级**条目

Day 30 的体检总表用「代码取证（B 级）」判了 8 个索引「有效」。
**本日证明了 B 级不足以判「有效」** —— `idx_user_coupons_user_id` 就是 B 级判错的活例。

⇒ 这 8 个都可能藏着同类问题：
`idx_products_brand_id` · `idx_product_images_product_id` · `idx_payments_order_id` ·
`idx_user_addresses_user_id` · `idx_cart_items_user_id` · `idx_cart_items_sku_id` ·
`idx_reviews_user_id` · `idx_admin_roles_role_id`

**方法已经现成**：本日的 DROP 实验（Day 31 写的）可以直接套。
★ 但**先别急着做** —— 判据是「写入成本是不是白付」：
这 8 个里若有人是**以复合索引为前缀**的（像本日这个），才是真冗余；
其余多半是正常的单列外键索引，测了也是「有效」。**优先测「可能有复合索引覆盖它」的那几个。**

### 5.3 优先级不变

1. ★ **实现 Day 28 的搜索修复** —— 仍是唯一有量级收益的一条（**29x**）。
2. 写 `backend/sql/15-drop-dead-indexes.sql`：现在候选从 3 个变成 **5 个**
   （原 3 个 + 本日的 `idx_coupons_status` / `idx_user_coupons_user_id`）。
3. 挂 CI：`day27` / `day28` / `day29` / `day31` / `day32` / `day33`。
4. 按 §5.2 补测 B 级里「疑似被复合索引覆盖」的那几个。

---

## 六、复现

```bash
cd backend/loadtest
python day33-coupon-status-probe.py     # 19/19
```
