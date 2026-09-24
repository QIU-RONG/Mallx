-- ============================================================
-- MallX 权限补发（Day 23 · RBAC 权限管理）—— 管理员 / 角色 / 权限
-- 说明：需在 01-schema / 02-index / 03-data / 05 / 07 / 08 / 10 / 12 之后执行。
--       幂等：可重复执行；只【增】权限与授权，不改既有任何一行。
-- ============================================================
--
-- ★★ 这是本项目【第 7 次】做同一件事（05 订单+库存 / 07 商品+分类 /
--    08 优惠券 / 10 品牌 / 12 用户+仪表盘 / 今次 RBAC）。失败模式每次都一样：
--
--      03-data.sql 的授权是「按 code 前缀批量授」且【只在首次种子时跑过一次】。
--      今天新增 admin:* / role:* / permission:* 时那几条 LIKE 不会再跑
--      → 权限行进表了，role_permissions 里没有一行指向它们
--      → @PreAuthorize 【永远 403】，而现象长得像「权限码拼错了」。
--
-- ★★ 本次【唯一的原则】：这 13 条码【一条都不给非超管】。
--    这不是「超管本来就什么都有」的顺带结果，而是一条硬性推理：
--      role:assign-permission   → 可以给自己所属的角色补满任意权限
--      admin:create + admin:assign-role → 可以造一个新超管账号
--    ⇒ 这三个域只要漏给任何一个非超管角色，RBAC 的门就【形同虚设】。
--    所以本文件的第二节【只有一段 INSERT】，且它只写给 role 1。
-- ============================================================

-- ------------------------------------------------------------
-- 一、新增 13 条权限（id 26..38）
-- ------------------------------------------------------------
-- id 接在 12-day22-permissions.sql 的 25 之后（那边也是显式 id）。
-- method / path 与真实端点逐字对应，逐条列出，不合并。
--
-- ★ 为什么分三组、各组的条数不一样：
--   管理员 6 条（5 个 CRUD + 1 个分配角色）
--   角色   6 条（5 个 CRUD + 1 个分配权限）
--   权限   1 条（只有 list —— 权限码是代码资产，不给界面 CRUD，见 Day-23 文档 §一 决策 1）
--   ⇒ 合计 6 + 6 + 1 = 13
--
-- ★ 为什么 admin / role 各拆 5 条 CRUD、不给「status 单独一码」：
--   Day 22 给 user:status 单开一码，是因为「订单管理员能看用户、但不该禁用」
--   —— 存在【两个人需要不同粒度】的真实需求。
--   而本日这 13 条【全部只发给超管】，没有第二个角色需要区分粒度
--   ⇒ 再拆码是纯粹的码数量膨胀。（这类与既有做法不一致的地方要写下来，
--     别让后来者以为是漏了。）
--
-- ⚠️ 落地前已实测核对：现有 25 条码里【没有】admin: / role: / permission: 前缀
--    ⇒ 下面的 WHERE NOT EXISTS (code) 不会与既有任何一条相撞。
INSERT INTO permissions (id, name, code, type, path, method)
SELECT v.id, v.name, v.code, v.type, v.path, v.method
FROM (VALUES
    (26, '管理员列表',     'admin:list',              'API', '/api/admin/admins',              'GET'),
    (27, '管理员详情',     'admin:detail',            'API', '/api/admin/admins/*',            'GET'),
    (28, '新建管理员',     'admin:create',            'API', '/api/admin/admins',              'POST'),
    (29, '编辑管理员',     'admin:update',            'API', '/api/admin/admins/*',            'PUT'),
    (30, '删除管理员',     'admin:delete',            'API', '/api/admin/admins/*',            'DELETE'),
    (31, '分配管理员角色', 'admin:assign-role',       'API', '/api/admin/admins/*/roles',      'PUT'),
    (32, '角色列表',       'role:list',               'API', '/api/admin/roles',               'GET'),
    (33, '角色详情',       'role:detail',             'API', '/api/admin/roles/*',             'GET'),
    (34, '新建角色',       'role:create',             'API', '/api/admin/roles',               'POST'),
    (35, '编辑角色',       'role:update',             'API', '/api/admin/roles/*',             'PUT'),
    (36, '删除角色',       'role:delete',             'API', '/api/admin/roles/*',             'DELETE'),
    (37, '分配角色权限',   'role:assign-permission',  'API', '/api/admin/roles/*/permissions', 'PUT'),
    (38, '权限字典',       'permission:list',         'API', '/api/admin/permissions',         'GET')
) AS v(id, name, code, type, path, method)
WHERE NOT EXISTS (SELECT 1 FROM permissions p WHERE p.code = v.code);

-- ★ 存在性判断用【code】而非 id：code 上有 UNIQUE 约束，用 code 判断即使有人手工
--   挪过 id 也依然幂等。⚠️ 反过来说：显式指定 id 的种子【必须】校准序列（见第三节）。

-- ------------------------------------------------------------
-- 二、补发授权（★ 本次只有一段，且只写给 role 1）
-- ------------------------------------------------------------

-- ★★ 超级管理员（role 1）：拿这三域的全部 13 条。
--    写法沿用 03-data.sql / 12 的「role 1 拿全部」式（不写死 id 列表，
--    所以将来再新增权限，重跑本文件即可自动补上）。
--    ⚠️ 但注意它【只覆盖这三个前缀】，不是「全表全部」——
--       刻意收窄到这个范围，是为了让「本文件干了什么」在阅读时一目了然
--       （全表式授权请见 12-day22-permissions.sql 第①节，那个仍然是全表的口子）。
INSERT INTO role_permissions (role_id, permission_id)
SELECT 1, p.id
FROM permissions p
WHERE (p.code LIKE 'admin:%' OR p.code LIKE 'role:%' OR p.code LIKE 'permission:%')
  AND NOT EXISTS (SELECT 1 FROM role_permissions rp
                   WHERE rp.role_id = 1 AND rp.permission_id = p.id);

-- ★★ 商品管理员（role 2）与订单管理员（role 3）：【一条都不给】。
--
--    这里【故意不写 INSERT】—— 与 12 第④节「刻意留白」同一手法。
--    理由（要能自证）：三条码合起来是完整的【自我提权通道】
--      admin:create + admin:assign-role  ⇒ 造一个新超管账号
--      role:assign-permission            ⇒ 给自己所属角色补满任意权限
--    ⇒ 给任何一个非超管角色发其中任意一条，RBAC 就只剩装饰作用。
--
--    验收里的反向对照（Day 17 夹具 op_product / op_order 不用白不用）：
--      op_product（PRODUCT_ADMIN）打 /api/admin/roles   → 期望 403
--      op_order  （ORDER_ADMIN）  打 /api/admin/admins  → 期望 403
--    ★ 只用全权 admin 测 = 什么都证明不了 —— 那两个账号存在的全部意义。

-- ------------------------------------------------------------
-- 三、序列校准（★ 与 03-data.sql 末尾、05/07/08/10/12 同一件事）
-- ------------------------------------------------------------
-- 上面用显式 id 插入 26..38，PG 的序列不会因此前进 → 必须推到 MAX(id)。
-- 漏了它的现象：业务侧下一次 INSERT 拿到 nextval=26，撞上已存在的 id → 23505。
SELECT setval(pg_get_serial_sequence('permissions', 'id'),
              COALESCE((SELECT MAX(id) FROM permissions), 1));

-- ------------------------------------------------------------
-- 四、自检（执行后请人工核对这四段输出）
-- ------------------------------------------------------------

-- 4.1 本日新增的 13 条是否在、path/method 是否逐字对齐
SELECT id, code, name, path, method
  FROM permissions
 WHERE code LIKE 'admin:%' OR code LIKE 'role:%' OR code LIKE 'permission:%'
 ORDER BY id;
-- ★ 期望 13 行：id 26..38，且 path 全部指向 /api/admin/**。
-- ⚠️ 若某行的 path 指向 /api/**（少了 admin 段）⇒ 权限表在说谎，
--    下一个人照着它去猜端点会猜错（同 Day 22 订正 user:list 的教训）。

-- 4.2 谁拿到了什么（按角色汇总）
SELECT r.code AS role_code,
       count(*)                                AS perm_count,
       string_agg(p.code, ', ' ORDER BY p.code) AS perms
  FROM role_permissions rp
  JOIN roles       r ON r.id = rp.role_id
  JOIN permissions p ON p.id = rp.permission_id
 WHERE p.code LIKE 'admin:%' OR p.code LIKE 'role:%' OR p.code LIKE 'permission:%'
 GROUP BY r.code
 ORDER BY r.code;
-- ★ 期望【只有一行】：SUPER_ADMIN / 13 / 那 13 个码。
-- ⚠️ 若出现 PRODUCT_ADMIN 或 ORDER_ADMIN 的行 ⇒ 授权发多了，
--    等于开了一条自我提权通道（本文件第二节的推理）。

-- 4.3 ★ 最关键的一行：这六列【必须】是
--        6 / 6 / 1 / 13 / 0 / 0
--     左一：admin 权限总数 = 6
--     左二：role 权限总数 = 6
--     左三：permission 权限总数 = 1
--     左四：role 1（SUPER_ADMIN）拿到的 = 13
--           ★ 复算：左四 = 左一 + 左二 + 左三 = 6 + 6 + 1 = 13
--             （凡「合计」类期望值，都要能从别的格子复算出来，别凭印象填 ——
--              这条纪律在 12 的同类注释里写着，本次是它第 2 次被引用）
--     左五：role 2（PRODUCT_ADMIN）拿到的 = 0  ★★ 期望就是 0（反向对照）
--     左六：role 3（ORDER_ADMIN）拿到的   = 0  ★★ 期望就是 0（反向对照）
--     ⚠️ 若左四 < 13 ⇒ 本日 13 个端点对超管会稳定 403；
--        若左五 / 左六 > 0 ⇒ 权限给多了，越权通道已开。
SELECT (SELECT count(*) FROM permissions WHERE code LIKE 'admin:%')                      AS admin_perms_total,
       (SELECT count(*) FROM permissions WHERE code LIKE 'role:%')                       AS role_perms_total,
       (SELECT count(*) FROM permissions WHERE code LIKE 'permission:%')                 AS perm_perms_total,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 1
           AND (p.code LIKE 'admin:%' OR p.code LIKE 'role:%' OR p.code LIKE 'permission:%')) AS role1_rbac,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 2
           AND (p.code LIKE 'admin:%' OR p.code LIKE 'role:%' OR p.code LIKE 'permission:%')) AS role2_rbac,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 3
           AND (p.code LIKE 'admin:%' OR p.code LIKE 'role:%' OR p.code LIKE 'permission:%')) AS role3_rbac;

-- 4.4 权限总数（应 = 38，max_id 也应 = 38）
SELECT count(*) AS permissions_total, max(id) AS max_id FROM permissions;
-- ★ 25（Day 22 收口时）+ 13（本日）= 38。
-- ⚠️ 若 max_id > 38 ⇒ 序列之外的插入发生了；若 < 38 ⇒ 第一节没跑完。
