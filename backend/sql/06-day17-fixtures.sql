-- ============================================================================
-- 06-day17-fixtures.sql —— Day 17 验收夹具（★ 测试数据，不是生产种子）
-- ============================================================================
-- 为什么必须有这个账号（不是"顺手多加个用户"，而是某条断言【没它就做不出来】）：
--
--   现有唯一管理员 admin(id = 1) 是 SUPER_ADMIN、拥有全部权限。
--   它【证明不了】@PreAuthorize 里的权限码真的在生效 —— 写错、写漏、写反，它都照样 200。
--
--   而验收里有两类断言，只有"有 order:* 但没有 inventory:*"的账号才做得出来：
--
--     ① 权限矩阵的区分度
--          op_order 打订单端点   → 200
--          op_order 打库存端点   → 403     ← 同一个 token，两种结果
--        没有它，"6 端点 × 4 身份"退化成"6 端点 × 1 个全权限账号"，全是 200，毫无信息量。
--
--     ② ★★ 管理端详情「不过滤归属」的硬证据（本日核心概念的直接检验）
--        实测数据：admins.id = 1，而 orders.user_id 也全是 1 —— 两个数字【撞在一起】。
--        后果：若有人把 detailByAdmin 错写成
--              requireOwn(当前登录管理员的 id, orderId)
--        因为 1 = 1 会【照样返回 200】，用 admin 当测试账号永远发现不了这个降级。
--
--        op_order 的 id ≠ 1（它由序列分配），用它去取 user_id = 1 的订单：
--              正确实现 → 200（管理员有权看任何人的单）
--              降级实现 → 404（被归属校验拦住）
--        这才是这条断言真正的判别力所在 —— 也是 03-data.sql 里只种一个管理员时
--        那个巧合埋下的坑（"空表跑得通 ≠ 逻辑对"的又一变体）。
--
-- 幂等：全部靠 NOT EXISTS，重复执行不新增任何行。
-- 序列：admins 是「显式 id 种子」表（见 03-data.sql §九 的说明），
--       不先校准序列就做"不指定 id 的 INSERT"，会直接撞已有主键 1。
-- ============================================================================

-- ① 先把 admins 序列推到当前最大 id（COALESCE 兜住空表的极端情况）
SELECT setval(pg_get_serial_sequence('admins', 'id'), COALESCE((SELECT MAX(id) FROM admins), 1));

-- ② 幂等插入 op_order —— 刻意【不显式给 id】，由序列分配，
--    于是它必然 ≠ admin 的 1（这正是判别力的来源，别改成硬编码 id）
INSERT INTO admins (username, password, nickname, status)
SELECT 'op_order', '{noop}op123456', '订单管理员(夹具)', 1
WHERE NOT EXISTS (SELECT 1 FROM admins a WHERE a.username = 'op_order');

-- ③ 挂角色 3 = ORDER_ADMIN（有 order:*，没有 inventory:*）
INSERT INTO admin_roles (admin_id, role_id)
SELECT a.id, 3
FROM admins a
WHERE a.username = 'op_order'
  AND NOT EXISTS (SELECT 1 FROM admin_roles ar WHERE ar.admin_id = a.id AND ar.role_id = 3);

-- ④ 幂等插入 op_product —— 商品管理员，库存端点的【正向】验证用它。
--    它与 op_order 构成一对【正反对照】：
--      op_order   打订单端点 200 / 打库存端点 403   （有 order:*，没有 inventory:*）
--      op_product 打库存端点 200 / 打订单端点 403   （有 inventory:*，没有 order:*）
--    同一个 token 打两个模块拿到两种结果，才说明 @PreAuthorize 里的权限码真的在生效；
--    admin（SUPER_ADMIN）两条都是 200，【证明不了】任何事。
INSERT INTO admins (username, password, nickname, status)
SELECT 'op_product', '{noop}prod123456', '商品管理员(夹具)', 1
WHERE NOT EXISTS (SELECT 1 FROM admins a WHERE a.username = 'op_product');

-- ⑤ 挂角色 2 = PRODUCT_ADMIN（有 inventory:list / adjust / log 与 product:*，没有 order:*）
INSERT INTO admin_roles (admin_id, role_id)
SELECT a.id, 2
FROM admins a
WHERE a.username = 'op_product'
  AND NOT EXISTS (SELECT 1 FROM admin_roles ar WHERE ar.admin_id = a.id AND ar.role_id = 2);

-- ⑥ 自检：把账号 / 角色 / 实际权限码打出来（人工核对，脚本也读这一段）
SELECT 'admins' AS t, a.id, a.username,
       COALESCE(string_agg(DISTINCT r.code, ',' ORDER BY r.code), '(无角色)') AS roles,
       COALESCE(string_agg(DISTINCT p.code, ',' ORDER BY p.code), '(无权限)') AS perms
FROM admins a
LEFT JOIN admin_roles ar ON ar.admin_id = a.id
LEFT JOIN roles r ON r.id = ar.role_id
LEFT JOIN role_permissions rp ON rp.role_id = r.id
LEFT JOIN permissions p ON p.id = rp.permission_id
GROUP BY a.id, a.username
ORDER BY a.id;
