-- ============================================================
-- MallX 权限补发（Day 20）—— 管理端优惠券
-- 说明：需在 01-schema / 02-index / 03-data / 05 / 07 之后执行。
--       幂等：可重复执行；只【增】权限与授权，历史种子一个字都不动。
-- ============================================================
--
-- ★★ 这是本项目【第 4 次】做同一件事（05 订单+库存 / 07 商品+分类 / 今次 优惠券）。
--    原因每次都一样：03-data.sql 的授权用的是「按 code 前缀批量授」——
--
--        INSERT INTO role_permissions (role_id, permission_id)
--        SELECT 2, p.id FROM permissions p WHERE p.code LIKE 'product:%'
--
--    它【只在首次种子时跑过一次】。今天新增 coupon:* 时那条 LIKE 不会再跑
--    → 新权限行进了 permissions 表，但 role_permissions 里没有一行指向它们
--    → @PreAuthorize("hasAuthority('coupon:create')") 【永远 403】。
--
--    ⚠️ 这个失败模式长得像「注解写错了」，实际是数据没补 —— 排查方向天然跑偏到 Java 侧。
--       所以第五节的自检 SQL 是必看的，不是可选。
-- ============================================================

-- ------------------------------------------------------------
-- 一、新增 3 条优惠券权限（id 18..20）
-- ------------------------------------------------------------
-- id 接在 07-admin-permissions.sql 的 14..17 之后（那边也是显式 id）。
-- method / path 与 AdminCouponController 的真实端点逐字对应。
--
-- ★ 为什么【只有 3 条】、没有 coupon:update：
--   券一旦发出去，改面额会与已领取用户的预期冲突（他领的是「满 100 减 20」，
--   你把面额改成 10，他手里那张算什么？）。真实系统的做法是「作废旧券 + 新建一张」，
--   不是原地改。所以 V1.0 就三件事：建 / 停（status 置 0，走 coupon:create 后的管理动作，不单设权限码）/ 删。
--   ⇒ 少一条永远不会被人使用的权限码 —— 权限码的数量本身就是维护成本（与 07 的取舍同源）。
INSERT INTO permissions (id, name, code, type, path, method)
SELECT v.id, v.name, v.code, v.type, v.path, v.method
FROM (VALUES
    (18, '优惠券列表', 'coupon:list',   'API', '/api/admin/coupons',   'GET'),
    (19, '新建优惠券', 'coupon:create', 'API', '/api/admin/coupons',   'POST'),
    (20, '删除优惠券', 'coupon:delete', 'API', '/api/admin/coupons/*', 'DELETE')
) AS v(id, name, code, type, path, method)
WHERE NOT EXISTS (SELECT 1 FROM permissions p WHERE p.code = v.code);

-- ★ 存在性判断用【code】而不是 id：code 上有 UNIQUE 约束（01-schema.sql:341），
--   而 id 只是个约定值。用 code 判断，即使有人手工挪过 id，本语句依然幂等。
-- ⚠️ 反过来说：显式指定 id 的种子【必须】校准序列（见第三节）。

-- ------------------------------------------------------------
-- 二、补发授权（★ 只给超管 —— 这是本文件的业务判断，不是省事）
-- ------------------------------------------------------------
-- ① 超级管理员（role 1）：拿【全部】权限 —— 不限前缀，
--    它要的语义就是「以后新增的权限也归我」。
--    ⚠️ 05 / 07 里已有同一条语句，这里再写一遍【不是冗余】：
--       它们只覆盖到「执行到它那一刻」存在的权限行；今天新增的 coupon:* 必须再补一次。
INSERT INTO role_permissions (role_id, permission_id)
SELECT 1, p.id
FROM permissions p
WHERE NOT EXISTS (SELECT 1 FROM role_permissions rp
                   WHERE rp.role_id = 1 AND rp.permission_id = p.id);

-- ② ★★ 商品管理员（role 2 / PRODUCT_ADMIN）与订单管理员（role 3 / ORDER_ADMIN）
--    【刻意一条都不给】。理由要说得出：
--
--      营销在 V1.0 是独立岗位。种子里的三个角色是「商品 / 订单 / 超管」，
--      没有 MARKETING_ADMIN —— 给商品管理员发券是【越权】，不是「顺手」。
--
--    ★ 这正是验收链路 H 的依据：admin → 200，op_product / op_order → 403。
--      权限矩阵的区分度全靠「谁没有」—— 给所有人都发一遍等于没有权限系统（Day 17 定型）。

-- ------------------------------------------------------------
-- 三、序列校准（★ 与 03-data.sql 末尾、05/07 同一件事）
-- ------------------------------------------------------------
-- 上面用显式 id 插入了 18..20，PG 的序列不会因此前进 → 必须推到 MAX(id)。
-- 漏了它的现象：业务侧下一次 INSERT 拿到 nextval=1，撞上已存在的 id → 23505。
SELECT setval(pg_get_serial_sequence('permissions', 'id'),
              COALESCE((SELECT MAX(id) FROM permissions), 1));

-- ------------------------------------------------------------
-- 四、路径自检（★ 顺带订正历史元数据）
-- ------------------------------------------------------------
-- 与 05 / 07 同一手法：只改「还停在旧值」的行，不覆盖别人手工订正过的值。
-- 本次无历史遗留需要订正（coupon 是本日全新的前缀），故此处只留一条巡检语句，
-- 供将来发现 path 漂移时复用：
--   SELECT id, code, path FROM permissions WHERE path LIKE '/api/coupons%' ORDER BY id;
-- ★ 期望 3 行，且 path 全部以 /api/admin/ 开头 —— 若出现 /api/coupons 则是写错了
--   （那会指向【C 端公开端点】，而 C 端压根不查权限码，等于一条死权限）。

-- ------------------------------------------------------------
-- 五、自检（执行后请人工核对这三段输出）
-- ------------------------------------------------------------

-- 5.1 三条权限是否都在，path 是否指向管理端
SELECT id, code, name, path, method
  FROM permissions
 WHERE code LIKE 'coupon:%'
 ORDER BY id;
-- ★ 期望 3 行：18 / 19 / 20，path 全部 /api/admin/coupons(/*)。

-- 5.2 谁拿到了什么
SELECT r.code AS role_code,
       count(*)                                AS perm_count,
       string_agg(p.code, ', ' ORDER BY p.code) AS perms
  FROM role_permissions rp
  JOIN roles       r ON r.id = rp.role_id
  JOIN permissions p ON p.id = rp.permission_id
 GROUP BY r.code
 ORDER BY r.code;

-- 5.3 ★ 最关键的一行：这四列【必须】是 3 / 3 / 3 / 0
--     左一：coupon 权限总数 = 3（list / create / delete）
--     左二：role 1（超管）拿到的 coupon 权限数 = 3
--     左三：role 2（PRODUCT_ADMIN）拿到的 coupon 权限数 = 0  ← 期望就是 0，反向对照
--     左四：role 3（ORDER_ADMIN）拿到的 coupon 权限数 = 0    ← 期望就是 0，反向对照
--     ⚠️ 若左二 ≠ 3 ⇒ @PreAuthorize 会稳定 403，接口怎么调都不通。
SELECT (SELECT count(*) FROM permissions p WHERE p.code LIKE 'coupon:%')                  AS coupon_perms_total,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 1 AND p.code LIKE 'coupon:%')                                 AS granted_to_super_admin,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 2 AND p.code LIKE 'coupon:%')                                 AS granted_to_product_admin,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 3 AND p.code LIKE 'coupon:%')                                 AS granted_to_order_admin;
