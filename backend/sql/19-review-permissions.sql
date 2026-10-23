-- ============================================================
-- MallX 权限补发（Day 55）—— 管理端评价审核
-- 说明：需在 01-schema / 02-index / 03-data / 05 / 07 / 08 / 10 / 12 / 13 / 14 / 17 / 18 之后执行。
--       幂等：可重复执行；只【增】权限与授权，不改既有任何一行。
-- ============================================================
--
-- ★★ 这是本项目【第 10 次】做同一件事。14 号文件头那条 ★ 一般化在这里同样成立：
--      「按前缀批量授权」只对「执行那一刻已存在的行」生效 ——
--      所以本文件自己就补发（跟着新增行一起执行），不指望以后有人回来补。
--
-- ★★ 本日的关键事实：reviews 表【早就有】status 列（01-schema.sql:247，NOT NULL DEFAULT 1），
--     C 端的两个列表与两个聚合早就写了 `AND status = 1`。
--     ⇒ 本日【不需要改表结构】，只是第一次有人能把它从 1 改成 0：
--       「隐藏评价」这条能力，三天前就已经在 SQL 里留好了位置，只是没有入口。
--     ★ 这正是「先定口径、后开入口」的价值：开入口时不碰任何既有读路径。
-- ============================================================

-- ------------------------------------------------------------
-- 一、新增 2 条评价权限（id 47..48）
-- ------------------------------------------------------------
-- id 接在 18-refund-permissions.sql 的 46 之后（那边也是显式 id）。
-- ★ 落笔前已核：SELECT max(id) FROM permissions = 46（46 + 2 = 48，保持 1..48 连续）。
-- method / path 与 AdminReviewController 的真实端点逐字对应。
INSERT INTO permissions (id, name, code, type, path, method)
SELECT v.id, v.name, v.code, v.type, v.path, v.method
FROM (VALUES
    (47, '评价列表', 'review:list',   'API', '/api/admin/reviews',            'GET'),
    (48, '评价显示/隐藏', 'review:status', 'API', '/api/admin/reviews/*/status', 'PUT')
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

-- ② 商品管理员（role 2 / PRODUCT_ADMIN）：只拿 review:list
--    ★ 理由：评价挂在商品页上，商品管理员要看得见「这件商品被说了什么」；
--      这是【读】权限，与他的日常（维护卖什么）同一域。
--    ★★ 但【不给 review:status】：隐藏一条评价会直接影响商品页的展示与评分，
--      属于「以平台身份改写用户表达」的治理动作 —— 与 user:status（禁用账号）
--      同级别，只留给超级管理员。这是验收里那组反向断言的依据。
INSERT INTO role_permissions (role_id, permission_id)
SELECT 2, p.id
FROM permissions p
WHERE p.code = 'review:list'
  AND NOT EXISTS (SELECT 1 FROM role_permissions rp
                   WHERE rp.role_id = 2 AND rp.permission_id = p.id);

-- ③ ★ 故意【不】给订单管理员（role 3 / ORDER_ADMIN）
--    订单管理员管的是「从下单到收货」，评价发生在收货之后、且改的是商品页内容，
--    不是订单生命周期的一环。给他发 = 让一个无关岗位持有内容治理权限。
--    ★ 权限矩阵的区分度全靠「谁没有」—— 给所有人都发一遍等于没有权限系统。

-- ------------------------------------------------------------
-- 三、序列校准（★ 与 03-data.sql 末尾及 05/07/08/10/12/13/14/18 同一件事）
-- ------------------------------------------------------------
-- 上面用显式 id 插入 47..48，PG 的序列不会因此前进 → 必须推到 MAX(id)。
-- 漏了它的现象：业务侧下一次 INSERT 拿到 nextval=47，撞上已存在的 id → 23505。
SELECT setval(pg_get_serial_sequence('permissions', 'id'),
              COALESCE((SELECT MAX(id) FROM permissions), 1));

-- ------------------------------------------------------------
-- 四、自检（执行后请人工核对这三段输出）
-- ------------------------------------------------------------

-- 4.1 本日新增的 2 条是否在、path/method 是否逐字对齐
SELECT id, code, name, path, method
  FROM permissions
 WHERE code LIKE 'review:%'
 ORDER BY id;
-- ★ 期望 2 行：47 review:list / GET、48 review:status / PUT。
-- ⚠️ 若 path 少了 admin 段（/api/reviews/...）⇒ 权限表在说谎：
--    那指向的是【C 端端点】，而 C 端压根不查权限码，等于两条死权限。

-- 4.2 谁拿到了什么（按角色汇总）
SELECT r.code AS role_code,
       count(*)                                 AS perm_count,
       string_agg(p.code, ', ' ORDER BY p.code) AS perms
  FROM role_permissions rp
  JOIN roles       r ON r.id = rp.role_id
  JOIN permissions p ON p.id = rp.permission_id
 WHERE p.code LIKE 'review:%'
 GROUP BY r.code
 ORDER BY r.code;
-- ★ 期望【只有两行】：PRODUCT_ADMIN / 1 条（review:list）、SUPER_ADMIN / 2 条。
-- ⚠️ 若出现 ORDER_ADMIN 的行 ⇒ 授权发多了（本文件第二节③的推理）。

-- 4.3 ★ 最关键的一行：这四列【必须】是 2 / 2 / 1 / 0
--     左一：review 权限总数 = 2
--     左二：role 1（SUPER_ADMIN）  = 2
--     左三：role 2（PRODUCT_ADMIN）= 1   ← 只有 list
--     左四：role 3（ORDER_ADMIN）  = 0   ← 反向对照
--     ⚠️ 若左三 = 2 ⇒ 商品管理员拿到了隐藏评价的权限（越权治理）；
--        若左四 > 0 ⇒ 订单管理员被塞了内容治理权限。
SELECT (SELECT count(*) FROM permissions p WHERE p.code LIKE 'review:%')                    AS review_perms_total,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 1 AND p.code LIKE 'review:%')                                   AS role1_review,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 2 AND p.code LIKE 'review:%')                                   AS role2_review,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 3 AND p.code LIKE 'review:%')                                   AS role3_review;

-- 4.4 权限总数（应 = 48，max_id 也应 = 48）
SELECT count(*) AS permissions_total, max(id) AS max_id FROM permissions;
-- ★ 46（Day 46 收口时）+ 2（本日）= 48。
