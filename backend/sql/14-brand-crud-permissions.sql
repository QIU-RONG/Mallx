-- ============================================================
-- MallX 权限补发（Day 24 · L5②）—— 管理端品牌 CRUD
-- 说明：需在 01-schema / 02-index / 03-data / 05 / 07 / 08 / 10 / 12 / 13 之后执行。
--       幂等：可重复执行；只【增】权限与授权，不改既有任何一行。
-- ============================================================
--
-- ★★ 这是本项目【第 8 次】做同一件事（05 / 07 / 08 / 10 / 12 / 13 / 今次）。
--    失败模式每次都一样，而这次最容易被忽略，因为【10-brand-permissions.sql
--    看上去已经处理过品牌了】：
--
--      10 号文件只发了 brand:list 一条（那时 L5① 只交付字典查询），
--      它的第②节写的是  WHERE p.code LIKE 'brand:%'  ——
--      但那条语句【只在 Day 20 跑过一次】，今天新增的 39/40/41 不会再被它收养。
--      ⇒ 权限行进了 permissions 表，role_permissions 里没有一行指向它们
--      ⇒ @PreAuthorize("hasAuthority('brand:create')") 【永远 403】。
--
--    ★ 一般化：**「按前缀批量授权」只对「执行那一刻已存在的行」生效**。
--      看到 LIKE 'brand:%' 就以为「以后新增的 brand 权限会自动跟上」是错觉。
-- ============================================================

-- ------------------------------------------------------------
-- 一、新增 3 条品牌权限（id 39..41）
-- ------------------------------------------------------------
-- id 接在 13-day23-permissions.sql 的 38 之后（那边也是显式 id）。
-- method / path 与 AdminBrandController 的真实端点逐字对应。
--
-- ★ 为什么是 39 而不是 backlog 原文写的 22/23/24：
--   backlog 的 L5 条目写在 Day 20，当时 permissions 的 max id = 21。
--   之后 Day 22 拿走 22..25（user:detail / user:status / dashboard:overview / user:list）、
--   Day 23 拿走 26..38（admin:* / role:* / permission:*）⇒ 【现 max = 38】。
--   ★ 教训：清单里写死的 id 会随时间失效，落笔前必须 `SELECT max(id) FROM permissions`
--     实测一次（本次已实测）。
INSERT INTO permissions (id, name, code, type, path, method)
SELECT v.id, v.name, v.code, v.type, v.path, v.method
FROM (VALUES
    (39, '新建品牌', 'brand:create', 'API', '/api/admin/brands',   'POST'),
    (40, '编辑品牌', 'brand:update', 'API', '/api/admin/brands/*', 'PUT'),
    (41, '删除品牌', 'brand:delete', 'API', '/api/admin/brands/*', 'DELETE')
) AS v(id, name, code, type, path, method)
WHERE NOT EXISTS (SELECT 1 FROM permissions p WHERE p.code = v.code);

-- ★ 存在性判断用【code】而非 id：code 上有 UNIQUE 约束，用 code 判断即使有人手工
--   挪过 id 也依然幂等。⚠️ 反过来说：显式指定 id 的种子【必须】校准序列（见第三节）。

-- ------------------------------------------------------------
-- 二、补发授权
-- ------------------------------------------------------------
-- ★★ 发给谁：【超管 + 商品管理员】，与 10 号文件的 brand:list 保持同一判断。
--    理由是硬的：品牌是【商品域】的字典（products.brand_id → brands.id），
--    「谁维护商品，谁维护商品挂的品牌」是同一条业务边界
--    （与 07 号文件「商品与分类本来就是同一个岗位的活」同源）。
--    ★ 反过来，这条理由【不适用】于订单管理员（role 3）—— 他既不建商品、也不建品牌，
--      给他发等于让一个无关岗位持有商品域的写权限。
--    ★ 对照 13 号文件（RBAC 的 13 条【只发超管】）：那次是「自我提权通道」，
--      这次是「岗位边界」—— 两次都不约而同地没给 role 2/3，但理由完全不同。
--      写清楚理由，才不会让下一个人以为「反正都是超管专用」而照抄。

-- ① 超级管理员（role 1）：拿【全部】权限 —— 不限前缀，
--    它要的语义就是「以后新增的权限也归我」。
INSERT INTO role_permissions (role_id, permission_id)
SELECT 1, p.id
FROM permissions p
WHERE NOT EXISTS (SELECT 1 FROM role_permissions rp
                   WHERE rp.role_id = 1 AND rp.permission_id = p.id);

-- ② 商品管理员（role 2 / PRODUCT_ADMIN）：拿 brand:*
--    ★ 这里【可以】用前缀式（与 10 号文件同一写法）：因为它跟着本文件一起执行，
--      「执行那一刻已存在的 brand 行」正好就是 list + 这三条，语义完整。
--      ⚠️ 但下次再新增 brand:* 时，仍需再补一个文件 —— 见文件头的 ★ 一般化。
INSERT INTO role_permissions (role_id, permission_id)
SELECT 2, p.id
FROM permissions p
WHERE p.code LIKE 'brand:%'
  AND NOT EXISTS (SELECT 1 FROM role_permissions rp
                   WHERE rp.role_id = 2 AND rp.permission_id = p.id);

-- ③ ★ 故意【不】给订单管理员（role 3 / ORDER_ADMIN）
--    这是验收里那组反向断言的依据：op_order 打 POST /api/admin/brands → 403。
--    权限矩阵的区分度全靠「谁没有」—— 给所有人都发一遍等于没有权限系统（Day 17 定型）。

-- ------------------------------------------------------------
-- 三、序列校准（★ 与 03-data.sql 末尾及 05/07/08/10/12/13 同一件事）
-- ------------------------------------------------------------
-- 上面用显式 id 插入 39..41，PG 的序列不会因此前进 → 必须推到 MAX(id)。
-- 漏了它的现象：业务侧下一次 INSERT 拿到 nextval=26，撞上已存在的 id → 23505。
SELECT setval(pg_get_serial_sequence('permissions', 'id'),
              COALESCE((SELECT MAX(id) FROM permissions), 1));

-- ------------------------------------------------------------
-- 四、自检（执行后请人工核对这三段输出）
-- ------------------------------------------------------------

-- 4.1 本日新增的 3 条是否在、path/method 是否逐字对齐
SELECT id, code, name, path, method
  FROM permissions
 WHERE code LIKE 'brand:%'
 ORDER BY id;
-- ★ 期望 4 行：id 21（list，Day 20）+ 39 / 40 / 41（本日）。
-- ⚠️ 若 39/40/41 的 path 指向 /api/brands（少了 admin 段）⇒ 权限表在说谎：
--    那指向的是【C 端公开端点】，而 C 端压根不查权限码，等于三条死权限
--    （同 10 号文件的自检注释）。

-- 4.2 谁拿到了什么（按角色汇总）
SELECT r.code AS role_code,
       count(*)                                 AS perm_count,
       string_agg(p.code, ', ' ORDER BY p.code) AS perms
  FROM role_permissions rp
  JOIN roles       r ON r.id = rp.role_id
  JOIN permissions p ON p.id = rp.permission_id
 WHERE p.code LIKE 'brand:%'
 GROUP BY r.code
 ORDER BY r.code;
-- ★ 期望【只有两行】：SUPER_ADMIN / 4 条、PRODUCT_ADMIN / 4 条。
-- ⚠️ 若出现 ORDER_ADMIN 的行 ⇒ 授权发多了（本文件第二节③的推理）。

-- 4.3 ★ 最关键的一行：这四列【必须】是 4 / 4 / 4 / 0
--     左一：brand 权限总数 = 4（1 条 list + 本日 3 条）
--     左二：role 1（SUPER_ADMIN）拿到的 = 4
--     左三：role 2（PRODUCT_ADMIN）拿到的 = 4
--           ★ 复算：左一 = 左二 = 左三 = 1 + 3 = 4
--     左四：role 3（ORDER_ADMIN）拿到的 = 0   ← 期望就是 0，反向对照
--     ⚠️ 若左三 < 4 ⇒ 本日 3 个写端点对商品管理员会稳定 403；
--        若左四 > 0 ⇒ 越权（订单管理员拿到了商品域写权限）。
SELECT (SELECT count(*) FROM permissions p WHERE p.code LIKE 'brand:%')                    AS brand_perms_total,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 1 AND p.code LIKE 'brand:%')                                   AS role1_brand,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 2 AND p.code LIKE 'brand:%')                                   AS role2_brand,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 3 AND p.code LIKE 'brand:%')                                   AS role3_brand;

-- 4.4 权限总数（应 = 41，max_id 也应 = 41）
SELECT count(*) AS permissions_total, max(id) AS max_id FROM permissions;
-- ★ 38（Day 23 收口时）+ 3（本日）= 41。
-- ⚠️ 若 max_id > 41 ⇒ 序列之外的插入发生了；若 < 41 ⇒ 第一节没跑完。
