-- ============================================================
-- MallX 权限补发（Day 46）—— 管理端退款/售后
-- 说明：需在 01-schema / 02-index / 03-data / 05 / 07 / 08 / 10 / 12 / 13 / 14 / 17 之后执行。
--       幂等：可重复执行；只【增】权限与授权，不改既有任何一行。
-- ============================================================
--
-- ★★ 这是本项目【第 9 次】做同一件事。14 号文件头那条 ★ 一般化在这里同样成立：
--      「按前缀批量授权」只对「执行那一刻已存在的行」生效。
--      本次直接在同一个文件里补发（跟着新增行一起执行），语义完整。
--
-- ★ 本次的【反向对照】换了角色：14 号文件不给的是订单管理员（role 3），
--   这次不给的是【商品管理员（role 2）】——
--   理由见第二节③：**售后是订单域的延续**，不是商品域的。
-- ============================================================

-- ------------------------------------------------------------
-- 一、新增 5 条退款权限（id 42..46）
-- ------------------------------------------------------------
-- id 接在 14-brand-crud-permissions.sql 的 41 之后（那边也是显式 id）。
-- ★ 落笔前已实测：SELECT max(id) FROM permissions = 41。
-- method / path 与 AdminRefundController 的真实端点逐字对应。
INSERT INTO permissions (id, name, code, type, path, method)
SELECT v.id, v.name, v.code, v.type, v.path, v.method
FROM (VALUES
    (42, '退款单列表', 'refund:list',    'API', '/api/admin/refunds',            'GET'),
    (43, '退款审核通过', 'refund:approve', 'API', '/api/admin/refunds/*/approve', 'POST'),
    (44, '退款审核拒绝', 'refund:reject',  'API', '/api/admin/refunds/*/reject',  'POST'),
    (45, '退货确认收货', 'refund:receive', 'API', '/api/admin/refunds/*/receive', 'POST'),
    (46, '执行退款',    'refund:refund',  'API', '/api/admin/refunds/*/refund',  'POST')
) AS v(id, name, code, type, path, method)
WHERE NOT EXISTS (SELECT 1 FROM permissions p WHERE p.code = v.code);

-- ★ 存在性判断用【code】而非 id：code 上有 UNIQUE 约束，即使有人手工挪过 id 也依然幂等。

-- ------------------------------------------------------------
-- 二、补发授权
-- ------------------------------------------------------------
-- ① 超级管理员（role 1）：拿【全部】权限 —— 不限前缀，语义就是「以后新增的也归我」。
INSERT INTO role_permissions (role_id, permission_id)
SELECT 1, p.id
FROM permissions p
WHERE NOT EXISTS (SELECT 1 FROM role_permissions rp
                   WHERE rp.role_id = 1 AND rp.permission_id = p.id);

-- ② 订单管理员（role 3 / ORDER_ADMIN）：拿 refund:*
--    ★★ 理由是硬的：**售后是订单域的延续** ——
--       退款单挂在 orders 上、金额来自 orders.pay_amount、退货回补的是这批货的库存、
--       退的是这单用掉的券。「谁管订单生命周期，谁管它的逆向生命周期」是同一条边界，
--       与 07 号文件「商品与分类本来就是同一个岗位的活」同构。
--    ★ 对照「发货（order:ship）」：发货也归 role 3，售后是它的逆向动作 ⇒ 同一岗位。
INSERT INTO role_permissions (role_id, permission_id)
SELECT 3, p.id
FROM permissions p
WHERE p.code LIKE 'refund:%'
  AND NOT EXISTS (SELECT 1 FROM role_permissions rp
                   WHERE rp.role_id = 3 AND rp.permission_id = p.id);

-- ③ ★ 故意【不】给商品管理员（role 2 / PRODUCT_ADMIN）
--    商品管理员维护的是「卖什么」，不碰「卖出去之后怎么退」——
--    给他发等于让一个无关岗位持有订单域的写权限（而退款是【动钱】的写权限，
--    比改商品名重得多）。
--    这是验收里那组反向断言的依据：op_product 打 POST /api/admin/refunds/*/approve → 403。
--    ★ 权限矩阵的区分度全靠「谁没有」—— 给所有人都发一遍等于没有权限系统。

-- ------------------------------------------------------------
-- 三、序列校准（★ 与 03-data.sql 末尾及 05/07/08/10/12/13/14 同一件事）
-- ------------------------------------------------------------
-- 上面用显式 id 插入 42..46，PG 的序列不会因此前进 → 必须推到 MAX(id)。
-- 漏了它的现象：业务侧下一次 INSERT 拿到 nextval=42，撞上已存在的 id → 23505。
SELECT setval(pg_get_serial_sequence('permissions', 'id'),
              COALESCE((SELECT MAX(id) FROM permissions), 1));

-- ------------------------------------------------------------
-- 四、自检（执行后请人工核对这三段输出）
-- ------------------------------------------------------------

-- 4.1 本日新增的 5 条是否在、path/method 是否逐字对齐
SELECT id, code, name, path, method
  FROM permissions
 WHERE code LIKE 'refund:%'
 ORDER BY id;
-- ★ 期望 5 行：42 / 43 / 44 / 45 / 46。
-- ⚠️ 若 path 少了 admin 段（/api/refunds/...）⇒ 权限表在说谎：
--    那指向的是【C 端端点】，而 C 端压根不查权限码，等于五条死权限。

-- 4.2 谁拿到了什么（按角色汇总）
SELECT r.code AS role_code,
       count(*)                                 AS perm_count,
       string_agg(p.code, ', ' ORDER BY p.code) AS perms
  FROM role_permissions rp
  JOIN roles       r ON r.id = rp.role_id
  JOIN permissions p ON p.id = rp.permission_id
 WHERE p.code LIKE 'refund:%'
 GROUP BY r.code
 ORDER BY r.code;
-- ★ 期望【只有两行】：ORDER_ADMIN / 5 条、SUPER_ADMIN / 5 条。
-- ⚠️ 若出现 PRODUCT_ADMIN 的行 ⇒ 授权发多了（本文件第二节③的推理）。

-- 4.3 ★ 最关键的一行：这四列【必须】是 5 / 5 / 0 / 5
--     左一：refund 权限总数 = 5
--     左二：role 1（SUPER_ADMIN）  = 5
--     左三：role 2（PRODUCT_ADMIN）= 0    ← 期望就是 0，反向对照
--     左四：role 3（ORDER_ADMIN）  = 5
--     ⚠️ 若左四 < 5 ⇒ 本日 4 个写端点对订单管理员会稳定 403；
--        若左三 > 0 ⇒ 越权（商品管理员拿到了动钱的权限）。
SELECT (SELECT count(*) FROM permissions p WHERE p.code LIKE 'refund:%')                    AS refund_perms_total,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 1 AND p.code LIKE 'refund:%')                                   AS role1_refund,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 2 AND p.code LIKE 'refund:%')                                   AS role2_refund,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 3 AND p.code LIKE 'refund:%')                                   AS role3_refund;

-- 4.4 权限总数（应 = 46，max_id 也应 = 46）
SELECT count(*) AS permissions_total, max(id) AS max_id FROM permissions;
-- ★ 41（Day 24 收口时）+ 5（本日）= 46。
