-- ============================================================
-- MallX 权限补发（Day 20 补漏 · L5①）—— 管理端品牌字典
-- 说明：需在 01-schema / 02-index / 03-data / 05 / 07 / 08 之后执行。
--       幂等：可重复执行；只【增】权限与授权，历史种子一个字都不动。
-- ============================================================
--
-- ★★ 这是本项目【第 5 次】做同一件事（05 订单+库存 / 07 商品+分类 /
--    08 优惠券 / 今次 品牌）。原因每次都一样，且这次的失败模式最容易误判：
--
--      03-data.sql 的授权用的是「按 code 前缀批量授」——
--
--          INSERT INTO role_permissions (role_id, permission_id)
--          SELECT 2, p.id FROM permissions p WHERE p.code LIKE 'product:%'
--
--      它【只在首次种子时跑过一次】。今天新增 brand:* 时那条 LIKE 不会再跑
--      → 新权限行进了 permissions 表，但 role_permissions 里没有一行指向它们
--      → @PreAuthorize("hasAuthority('brand:list')") 【永远 403】。
--
--    ⚠️ 这个失败模式长得像「@PreAuthorize 写错了 / 权限码拼错了」，
--       实际是数据没补 —— 排查方向天然跑偏到 Java 侧。所以第五节自检必看。
-- ============================================================

-- ------------------------------------------------------------
-- 一、新增 1 条品牌权限（id 21）
-- ------------------------------------------------------------
-- id 接在 08-marketing-permissions.sql 的 18..20 之后（那边也是显式 id）。
-- method / path 与 AdminBrandController 的真实端点逐字对应。
--
-- ★ 为什么【只加 list 一条】、不一次把 create/update/delete 也发出来：
--   本步（L5①）只交付「字典查询」。CRUD 是 L5 第②步，届时按同样的幂等模板补
--   22/23/24。★ 提前发权限码而端点还不存在，等于造出【指向空气的权限】——
--   它们会出现在权限管理界面上，被分配给某个人，然后点了没反应。
--   权限码的数量本身就是维护成本（同 07 对「分类上下架」的取舍）。
INSERT INTO permissions (id, name, code, type, path, method)
SELECT v.id, v.name, v.code, v.type, v.path, v.method
FROM (VALUES
    (21, '品牌列表', 'brand:list', 'API', '/api/admin/brands', 'GET')
) AS v(id, name, code, type, path, method)
WHERE NOT EXISTS (SELECT 1 FROM permissions p WHERE p.code = v.code);

-- ★ 存在性判断用【code】而不是 id：code 上有 UNIQUE 约束（01-schema.sql:341），
--   而 id 只是个约定值。用 code 判断，即使有人手工挪过 id，本语句依然幂等。
-- ⚠️ 反过来说：显式指定 id 的种子【必须】校准序列（见第三节）。

-- ------------------------------------------------------------
-- 二、补发授权
-- ------------------------------------------------------------
-- ★ 判断依据：品牌是【商品域】的字典（products.brand_id → brands.id），
--   与 07 里「商品与分类本来就是同一个岗位的活」是同一条理由。
--   ⇒ 发给 ①超管 与 ②商品管理员（PRODUCT_ADMIN）两方。
--   ⚠️ 这与 08（优惠券）刻意【只发超管】形成对照 —— 那次的理由是
--      「营销在 V1.0 是独立岗位」，不能顺手给商品管理员。两次的判断不同，
--      恰恰说明「发给谁」是一个要说出理由的业务决定，不是模板动作。

-- ① 超级管理员（role 1）：拿【全部】权限 —— 不限前缀，
--    它要的语义就是「以后新增的权限也归我」。
INSERT INTO role_permissions (role_id, permission_id)
SELECT 1, p.id
FROM permissions p
WHERE NOT EXISTS (SELECT 1 FROM role_permissions rp
                   WHERE rp.role_id = 1 AND rp.permission_id = p.id);

-- ② 商品管理员（role 2 / PRODUCT_ADMIN）：拿 brand:*
INSERT INTO role_permissions (role_id, permission_id)
SELECT 2, p.id
FROM permissions p
WHERE p.code LIKE 'brand:%'
  AND NOT EXISTS (SELECT 1 FROM role_permissions rp
                   WHERE rp.role_id = 2 AND rp.permission_id = p.id);

-- ③ ★ 故意【不】给订单管理员（role 3 / ORDER_ADMIN）
--    这是验收里那组反向断言的依据：op_order 打 /api/admin/brands → 403。
--    权限矩阵的区分度全靠「谁没有」—— 给所有人都发一遍等于没有权限系统（Day 17 定型）。

-- ------------------------------------------------------------
-- 三、序列校准（★ 与 03-data.sql 末尾、05/07/08 同一件事）
-- ------------------------------------------------------------
-- 上面用显式 id 插入了 21，PG 的序列不会因此前进 → 必须推到 MAX(id)。
-- 漏了它的现象：业务侧下一次 INSERT 拿到 nextval=1，撞上已存在的 id → 23505。
SELECT setval(pg_get_serial_sequence('permissions', 'id'),
              COALESCE((SELECT MAX(id) FROM permissions), 1));

-- ------------------------------------------------------------
-- 四、路径自检（巡检用，不产生写入）
-- ------------------------------------------------------------
-- ★ 期望 1 行，path = /api/admin/brands —— 若出现 /api/brands 则是写错了
--   （那会指向【C 端公开端点】，而 C 端压根不查权限码，等于一条死权限）。
--   SELECT id, code, path FROM permissions WHERE code LIKE 'brand:%' ORDER BY id;

-- ------------------------------------------------------------
-- 五、自检（执行后请人工核对这三段输出）
-- ------------------------------------------------------------

-- 5.1 权限行是否在、path 是否指向管理端
SELECT id, code, name, path, method
  FROM permissions
 WHERE code LIKE 'brand:%'
 ORDER BY id;
-- ★ 期望 1 行：id 21，path = /api/admin/brands。

-- 5.2 谁拿到了什么
SELECT r.code AS role_code,
       count(*)                                AS perm_count,
       string_agg(p.code, ', ' ORDER BY p.code) AS perms
  FROM role_permissions rp
  JOIN roles       r ON r.id = rp.role_id
  JOIN permissions p ON p.id = rp.permission_id
 GROUP BY r.code
 ORDER BY r.code;

-- 5.3 ★ 最关键的一行：这四列【必须】是 1 / 1 / 1 / 0
--     左一：brand 权限总数 = 1（只交付 list）
--     左二：role 1（超管）拿到的 brand 权限数 = 1
--     左三：role 2（PRODUCT_ADMIN）拿到的 brand 权限数 = 1
--     左四：role 3（ORDER_ADMIN）拿到的 brand 权限数 = 0   ← 期望就是 0，反向对照
--     ⚠️ 若左二或左三 ≠ 1 ⇒ @PreAuthorize 会稳定 403，接口怎么调都不通。
SELECT (SELECT count(*) FROM permissions p WHERE p.code LIKE 'brand:%')                    AS brand_perms_total,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 1 AND p.code LIKE 'brand:%')                                   AS granted_to_super_admin,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 2 AND p.code LIKE 'brand:%')                                   AS granted_to_product_admin,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 3 AND p.code LIKE 'brand:%')                                   AS granted_to_order_admin;
