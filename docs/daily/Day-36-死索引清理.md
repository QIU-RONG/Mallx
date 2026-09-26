# Day 36 · 死索引清理 —— 16 号补丁（7 个零读收益的索引下线）

> 证据链：Day 30/31（products 侧 EXPLAIN 复盘）→ Day 33（券侧两种冗余）→
> Day 34（购物车两种冗余）→ Day 35（写入成本探针 19/19）。
> 四天取证，一天动手。

## 一、删了什么（`backend/sql/16-drop-dead-indexes.sql`）

| 索引 | 类型 | 证据 | 一句话理由 |
|---|---|---|---|
| `idx_products_status` | A 型 | Day 30/31 | status 取值域极小，planner 恒不选 |
| `idx_product_skus_is_deleted` | A 型 | Day 31 | 布尔列 ≈ 1 bit 选择性 |
| `idx_order_items_sku_id` | A 型 | Day 30/31 | 无接口按 sku_id 反查明细 |
| `idx_coupons_status` | A 型 | Day 33 | 同 products_status |
| `idx_cart_items_sku_id` | A 型 | Day 34 | 购物车写点全走 user_id |
| `idx_cart_items_user_id` | B 型 | Day 34 | 被 `uk_cart_user_sku(user_id,…)` 左前缀覆盖 |
| `idx_user_coupons_user_id` | B 型 | Day 33 | 被 09 号 `uk_user_coupons_user_coupon(user_id,…)` 左前缀覆盖 |

**刻意不动**：`idx_after_sales_*`、`idx_role_permissions_permission_id`、`idx_admin_roles_role_id`
（有真实查询在用）。

**口径（Day 35 探针的结论）**：删除理由是「零读收益的纯维护负担 + 有替代索引」的**卫生问题**，
不是省写入成本——探针证明单个二线索引的写入成本 ≤ 噪声，留着不炸，删了干净。

补丁自带 **DO 块自检**：7 个索引任一仍存在即 `RAISE EXCEPTION`（initdb 熔断语义下
「没跑到这」会立刻暴露，而不是安静地少删）。

## 二、联动改三处

1. **day25-sql-strict-check.py**：FILES/EXPECTED_FILES 15→16；VERDICT 措辞改动态 `% EXPECTED_FILES`。
2. **★★ 顺带修掉一个真雷**：day25 原来对**任何文件**的输出匹配 `SELF-CHECK OK` 就认定
   09 号探针活着——16 号补丁的同款 NOTICE 会**掩盖 09 的回归**（Day 25「健康检查正则被
   贪婪 `.*` 匹配到别的服务」的翻版）。已收窄为 `name == "09-user-coupons-unique.sql"`。
   教训同款：**判定字符串必须绑定它的来源**。
3. **README**：快速开始 for 循环 04–15→04–16、补丁表加 16 号行、day25 行 15 份→16 份、
   状态行 Day 01–35、版本规划 V1.2 标✅（核心完成）。

## 三、验收

- 开发库应用 16 号：7 × `DROP INDEX` + `NOTICE: SELF-CHECK OK`，exit 0。
- **day25 全新临时库 01→16：16/16**（含「磁盘上没有清单外的 .sql」护栏自动核对）。
- **day28-search-index-verify 复跑：15/15**（搜索计划不受死索引删除影响，符合预期——
  它们从未出现在计划里）。
- CI：Perf 审计脚本（day27–34）各自临时库形态不变；`initdb` 挂载同源 ⇒ 全新库自动少这 7 个索引。

## 四、方法论

- **删索引和建索引要用同一套证据标准**：建要 EXPLAIN 证明被用上，删也要 EXPLAIN 证明
  没被用上 + 有替代覆盖。Day 27–35 就是这条标准的完整闭环。
- 「XX 类自检字符串」必须在**产生它的文件范围内**判——否则新加一个同字符串的文件，
  旧断言就从「守卫」退化成「永真」。
