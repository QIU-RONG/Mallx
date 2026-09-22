-- ============================================================
-- MallX 权限补发（Day 18）—— 管理端商品 + 分类管理
-- 说明：需在 01-schema.sql、02-index.sql、03-data.sql、05-admin-permissions.sql 之后执行。
--       幂等：可重复执行；只【增】与【订正元数据】，03-data.sql 一个字都不动。
-- ============================================================
--
-- ★★ 本文件要解决两件事（一件是「补发」，一件是「订正」）：
--
--   【补发】category:* 是【全新】权限码 —— 03-data.sql 的权限种子里只有
--          product:* / order:* / user:list，压根没有 category 这回事。
--          新权限行进了 permissions 表，但 role_permissions 里没有任何一行指向它们
--          → @PreAuthorize("hasAuthority('category:create')") 永远 403。
--
--          03-data.sql 的授权语句用的是「按 code 前缀批量授」：
--
--              INSERT INTO role_permissions (role_id, permission_id)
--              SELECT 2, p.id FROM permissions p
--              WHERE p.code LIKE 'product:%'          -- PRODUCT_ADMIN
--
--          它【只在首次种子时跑过一次】，且前缀是 product → 今天的 category:* 它爱莫能助。
--          ★ 这个失败模式长得像「代码写错了」，实际是「数据没补」—— 排查方向天然跑偏到 Java 侧。
--
--   【订正】product:* 五条权限（id 1..5）的 path 全部指向【C 端】端点
--          （/api/products、/api/products/*）。Day 18 把写能力迁到了管理端，
--          这五条的真实归属变成 /api/admin/products(**)。
--          ★ 顺带一提：其中 product:list / product:detail 此前是【死权限】——
--            没有任何端点引用（C 端 GET 走白名单公开，根本不查权限码），
--            path 指向的 C 端 GET 端点从未受它们保护。今天它们才第一次真正上岗。
--
-- ⚠️ path 这一列当前【没有任何代码在读】（把门人是 Java 侧 @PreAuthorize 的权限码），
--    所以 path 写错不会造成故障 —— 但会让后来者按 path 找端点时找错地方。
--    05-admin-permissions.sql 里已因同一原因订正过两次（order:list / order:detail），
--    本文件是第三次：说明「元数据指向漂移」在这个项目里属于需要主动巡检的一类问题。
-- ============================================================

-- ------------------------------------------------------------
-- 一、订正 product:* 五条权限的 path（C 端 → 管理端）
-- ------------------------------------------------------------
-- 用 VALUES 联表一次改完五条，避免五段几乎相同的 UPDATE。
--
-- ★ 守卫写 AND p.path <> v.new_path（而不是每条写死旧值）：
--   ① 幂等 —— 第二次执行时 path 已等于新值，条件不成立 → 0 行，
--      不会反复刷新 updated_at（伪幂等会让「谁在什么时候改过」这条线索失效）；
--   ② 只动「还没到新值」的行 —— 万一有人手工订正过，本语句不覆盖。
UPDATE permissions p
   SET path       = v.new_path,
       updated_at = CURRENT_TIMESTAMP
  FROM (VALUES
      ('product:list',   '/api/admin/products'),
      ('product:detail', '/api/admin/products/*'),
      ('product:create', '/api/admin/products'),
      ('product:update', '/api/admin/products/*'),
      ('product:delete', '/api/admin/products/*')
  ) AS v(code, new_path)
 WHERE p.code = v.code
   AND p.path <> v.new_path;

-- ------------------------------------------------------------
-- 二、新增 4 条分类权限（id 14..17）
-- ------------------------------------------------------------
-- id 接在 05-admin-permissions.sql 的 9..13 之后（那边五条也是显式 id）。
-- method / path 与 AdminCategoryController 的真实端点逐字对应。
--
-- ★ 为什么【不给】分类单独造一个「上下架」权限码：
--   分类的 status 在 V1.0 没有任何消费方（C 端 tree 不做 status 过滤），
--   造了就是一条永远不会被人使用的权限 —— 权限码的数量本身就是维护成本。
-- ★ 同理，商品的上下架【不单独授权限码】：ProductUpdateDTO 里已经有 status 字段，
--   走 PUT /api/admin/products/{id} 即可，语义就是「编辑商品」（product:update）。
INSERT INTO permissions (id, name, code, type, path, method)
SELECT v.id, v.name, v.code, v.type, v.path, v.method
FROM (VALUES
    (14, '分类列表', 'category:list',   'API', '/api/admin/categories/tree', 'GET'),
    (15, '新建分类', 'category:create', 'API', '/api/admin/categories',      'POST'),
    (16, '编辑分类', 'category:update', 'API', '/api/admin/categories/*',    'PUT'),
    (17, '删除分类', 'category:delete', 'API', '/api/admin/categories/*',    'DELETE')
) AS v(id, name, code, type, path, method)
WHERE NOT EXISTS (SELECT 1 FROM permissions p WHERE p.code = v.code);

-- ★ 存在性判断用【code】而不是 id：code 上有 UNIQUE 约束（01-schema.sql:341），
--   而 id 只是个约定值。用 code 判断，即使有人手工挪过 id，本语句依然幂等。
-- ⚠️ 反过来说：显式指定 id 的种子【必须】校准序列（见第四节）。

-- ------------------------------------------------------------
-- 三、补发授权（★ 本文件的核心动作）
-- ------------------------------------------------------------
-- 语句形状与 03-data.sql、05-admin-permissions.sql 完全一致（SELECT + NOT EXISTS 双保险）。

-- ① 超级管理员（role 1）：拿【全部】权限 —— 不限前缀，
--    它要的语义就是「以后新增的权限也归我」。
--    ⚠️ 05 里已经有同一条语句，这里再写一遍不是冗余：05 只覆盖到「执行到它那一刻」存在
--       的权限行。今天新增的 category:* 若不再补一次，超管反而会缺这四条。
INSERT INTO role_permissions (role_id, permission_id)
SELECT 1, p.id
FROM permissions p
WHERE NOT EXISTS (SELECT 1 FROM role_permissions rp
                   WHERE rp.role_id = 1 AND rp.permission_id = p.id);

-- ② 商品管理员（role 2 / PRODUCT_ADMIN）：拿所有 category:*
--    ★ product:* 它在 03-data.sql 就已经拿到了（那次 LIKE 'product:%' 生效过），
--      本日只是把「分类」补齐 —— 商品与分类本来就是同一个岗位的活。
INSERT INTO role_permissions (role_id, permission_id)
SELECT 2, p.id
FROM permissions p
WHERE p.code LIKE 'category:%'
  AND NOT EXISTS (SELECT 1 FROM role_permissions rp
                   WHERE rp.role_id = 2 AND rp.permission_id = p.id);

-- ③ ★ 故意【不】给订单管理员（role 3）任何 product:* / category:*
--    这正是验收里那组反向断言的依据：
--      op_order  账号打 /api/admin/products  → 403
--      op_product 账号打 /api/admin/orders   → 403（Day 17 已验）
--    权限矩阵的区分度全靠「谁没有」来体现 —— 给所有人都发一遍等于没有权限系统。

-- ------------------------------------------------------------
-- 四、序列校准（★ 与 03-data.sql 末尾、05 第四节同一件事）
-- ------------------------------------------------------------
-- 上面用显式 id 插入了 14..17，PG 的序列不会因此前进 → 必须推到 MAX(id)。
-- 漏了它的现象：业务侧下一次 INSERT 拿到 nextval=1，撞上已存在的 id → 23505。
SELECT setval(pg_get_serial_sequence('permissions', 'id'),
              COALESCE((SELECT MAX(id) FROM permissions), 1));

-- ------------------------------------------------------------
-- 五、自检（执行后请人工核对这四段输出）
-- ------------------------------------------------------------

-- 5.1 产品/分类权限全景：path 是否已是管理端路径、id 是否有空洞
SELECT id, code, name, path, method
  FROM permissions
 WHERE code LIKE 'product:%' OR code LIKE 'category:%'
 ORDER BY id;
-- ★ 期望 9 行：id 1..5（product，path 已订正为 /api/admin/...）+ id 14..17（category）。

-- 5.2 订正是否彻底：★ 期望 0 行（还指向 C 端路径的 product 权限一条都不该剩）
SELECT id, code, path
  FROM permissions
 WHERE code LIKE 'product:%'
   AND path LIKE '/api/products%'
 ORDER BY id;

-- 5.3 谁拿到了什么
SELECT r.code AS role_code,
       count(*)                                AS perm_count,
       string_agg(p.code, ', ' ORDER BY p.code) AS perms
  FROM role_permissions rp
  JOIN roles       r ON r.id = rp.role_id
  JOIN permissions p ON p.id = rp.permission_id
 GROUP BY r.code
 ORDER BY r.code;

-- 5.4 ★ 最关键的一行：这四列【必须全部相等】，否则 @PreAuthorize 会稳定 403
--     左一：category 权限总数 = 4（list / create / update / delete）
--     左二：role 2（PRODUCT_ADMIN）拿到的 category 权限数 = 4
--     左三：role 1（超管）拿到的 category 权限数 = 4
--     左四：role 3（ORDER_ADMIN）拿到的 category 权限数 = 0  ← 这一列【期望就是 0】，是反向对照
SELECT (SELECT count(*) FROM permissions p WHERE p.code LIKE 'category:%')                     AS category_perms_total,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 2 AND p.code LIKE 'category:%')                                    AS granted_to_product_admin,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 1 AND p.code LIKE 'category:%')                                    AS granted_to_super_admin,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 3 AND p.code LIKE 'category:%')                                    AS granted_to_order_admin;
