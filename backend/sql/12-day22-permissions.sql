-- ============================================================
-- MallX 权限补发（Day 22 · 管理端补齐）—— 用户管理 + 仪表盘
-- 说明：需在 01-schema / 02-index / 03-data / 05 / 07 / 08 / 10 之后执行。
--       幂等：可重复执行；只【增】权限与授权 + 【订正一条】路径元数据。
-- ============================================================
--
-- ★★ 这是本项目【第 6 次】做同一件事（05 订单+库存 / 07 商品+分类 /
--    08 优惠券 / 10 品牌 / 今次 用户+仪表盘）。失败模式每次都一样：
--
--      03-data.sql 的授权是「按 code 前缀批量授」且【只在首次种子时跑过一次】。
--      今天新增 user:detail / user:status / dashboard:* 时那几条 LIKE 不会再跑
--      → 权限行进表了，role_permissions 里没有一行指向它们
--      → @PreAuthorize 【永远 403】，而现象长得像「权限码拼错了」。
--
-- ★★ 本次【新增一类动作】：订正既有权限的 path（第【一.5】节）。
--    这是「同一个业务概念，写入口与读出口必须同源」的第 N 次落地 ——
--    权限种子里 user:list 的 path 写着 C 端路径 /api/users，
--    而本日管理端用户列表落在 /api/admin/users。
--    ⚠️ 注意 path/method 两列【只是元数据】（给权限界面/文档看的），
--       @PreAuthorize 只认 code ⇒ 这条订正【不改变任何鉴权行为】，
--       但不改就等于权限表在说谎，下一个人照着它去猜端点会猜错。
-- ============================================================

-- ------------------------------------------------------------
-- 一、新增 4 条权限（id 22..25）
-- ------------------------------------------------------------
-- id 接在 10-brand-permissions.sql 的 21 之后（那边也是显式 id）。
-- method / path 与真实端点逐字对应，逐条列出，不合并。
--
-- ★ 为什么 id 22/23 给用户、24/25 给仪表盘，而不是按模块分组：
--   id 只是插入顺序的产物，不需要有语义（roles/permissions 的语义在 code 上）。
--   这里按「本日落地顺序」排：先用户管理（有写操作，要细分），再仪表盘（全只读）。
--
-- ★ 为什么 user 要拆成三条（list / detail / status）而仪表盘只拆两条：
--   拆分的依据是「有没有【不同的人需要不同粒度】」。
--   用户域有：列表与详情是「读」、禁用是「写」，读写风险不同 → 必须拆；
--   仪表盘两个端点都是只读汇总、发给同一批人 → 拆是因为项目约定「一个端点一个码」，
--   而不是因为权限矩阵需要（这条差异要诚实写下来）。
INSERT INTO permissions (id, name, code, type, path, method)
SELECT v.id, v.name, v.code, v.type, v.path, v.method
FROM (VALUES
    (22, '用户详情',     'user:detail',        'API', '/api/admin/users/*',        'GET'),
    (23, '禁用/启用用户', 'user:status',        'API', '/api/admin/users/*/status', 'PUT'),
    (24, '仪表盘概览',   'dashboard:overview',  'API', '/api/admin/dashboard/overview', 'GET'),
    (25, '仪表盘趋势',   'dashboard:trend',     'API', '/api/admin/dashboard/trend',    'GET')
) AS v(id, name, code, type, path, method)
WHERE NOT EXISTS (SELECT 1 FROM permissions p WHERE p.code = v.code);

-- ★ 存在性判断用【code】而非 id：code 上有 UNIQUE 约束，用 code 判断即使有人手工
--   挪过 id 也依然幂等。⚠️ 反过来说：显式指定 id 的种子【必须】校准序列（见第三节）。

-- ------------------------------------------------------------
-- 一.5、订正既有权限 user:list(id 8) 的 path
-- ------------------------------------------------------------
-- 订正前：/api/users        （C 端路径，Day 06 的练手端点）
-- 订正后：/api/admin/users  （本日新建的管理端端点）
--
-- ★ 同日实测（day22-sec-probe.py E4）确认过它当时确实是 /api/users。
-- ★ 为什么必须改：这个权限码【从 Day 06 起就没有任何端点在使用】——
--   C 端 /api/users 不挂 @PreAuthorize（C 端 token 无 perms，挂了必 403），
--   于是它成了一条【指向不存在职责的权限】。本日管理端用户列表落地后，
--   它才真正有了主人；把 path 同步过去，权限表与代码才重新对上。
-- ⚠️ 这条 UPDATE 不改变任何鉴权行为（只改元数据列），但它让
--   「permissions 表 = 系统对外接口的权限地图」这个承诺重新成立。
UPDATE permissions
   SET path = '/api/admin/users'
 WHERE code = 'user:list'
   AND path <> '/api/admin/users';

-- ------------------------------------------------------------
-- 二、补发授权（★ 每条都要说理由）
-- ------------------------------------------------------------

-- ① 超级管理员（role 1）：拿【全部】权限，不限前缀。
--    它要的语义就是「以后新增的权限也归我」——与 10 同一写法。
INSERT INTO role_permissions (role_id, permission_id)
SELECT 1, p.id
FROM permissions p
WHERE NOT EXISTS (SELECT 1 FROM role_permissions rp
                   WHERE rp.role_id = 1 AND rp.permission_id = p.id);

-- ② 订单管理员（role 3 / ORDER_ADMIN）：拿 user:list + user:detail，【不给】user:status。
--    ★ 理由：订单管理员的日常工作是发货与售后处理，需要核对【买家是谁】
--      （订单快照里只有收货人，账号信息要另查）⇒ 读是必要的。
--      而「禁用账号」是治理动作，一旦误用会让一个真实用户登不上、且影响面跨模块
--      ⇒ 只留给超管。这正是夹具 op_order 存在的意义：反向对照。
INSERT INTO role_permissions (role_id, permission_id)
SELECT 3, p.id
FROM permissions p
WHERE p.code IN ('user:list', 'user:detail')
  AND NOT EXISTS (SELECT 1 FROM role_permissions rp
                   WHERE rp.role_id = 3 AND rp.permission_id = p.id);

-- ③ 仪表盘（dashboard:*）发给【三个角色全部】。
--    ★ 理由（与 08 只发超管、10 只发超管+商品的对照）：仪表盘是
--      ① 只读汇总、② 不含任何个人敏感数据、③ 不含写操作；且粒度太粗
--      （总数/总额），无法反推出具体订单或用户 ⇒ 发给所有管理员不构成越权。
--    ⚠️ 但仍【每个端点一个权限码】（项目约定）—— 将来真要差异化时不必改代码。
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r CROSS JOIN permissions p
WHERE r.code IN ('SUPER_ADMIN', 'PRODUCT_ADMIN', 'ORDER_ADMIN')
  AND p.code LIKE 'dashboard:%'
  AND NOT EXISTS (SELECT 1 FROM role_permissions rp
                   WHERE rp.role_id = r.id AND rp.permission_id = p.id);

-- ④ ★ 故意【不】给商品管理员（role 2）任何 user:* 权限。
--    理由：商品侧的 V1.0 职责里没有「看用户」的场景（商品管理员不管买家）。
--    ⇒ op_product 打 /api/admin/users → 403 是验收里的反向对照。
--    ⚠️ 这是【刻意留白】，不是漏了 —— 与 10 第③节同一手法。

-- ------------------------------------------------------------
-- 三、序列校准（★ 与 03-data.sql 末尾、05/07/08/10 同一件事）
-- ------------------------------------------------------------
-- 上面用显式 id 插入 22..25，PG 的序列不会因此前进 → 必须推到 MAX(id)。
-- 漏了它的现象：业务侧下一次 INSERT 拿到 nextval=1，撞上已存在的 id → 23505。
SELECT setval(pg_get_serial_sequence('permissions', 'id'),
              COALESCE((SELECT MAX(id) FROM permissions), 1));

-- ------------------------------------------------------------
-- 四、自检（执行后请人工核对这四段输出）
-- ------------------------------------------------------------

-- 4.1 本日新增的 4 条是否在、path 是否指向管理端
SELECT id, code, name, path, method
  FROM permissions
 WHERE code LIKE 'dashboard:%' OR code IN ('user:list', 'user:detail', 'user:status')
 ORDER BY id;
-- ★ 期望 5 行：8（user:list，path 应为 /api/admin/users）、22、23、24、25。
-- ⚠️ 若 user:list 的 path 还是 /api/users ⇒ 一.5 那条 UPDATE 没生效。

-- 4.2 谁拿到了什么
SELECT r.code AS role_code,
       count(*)                                AS perm_count,
       string_agg(p.code, ', ' ORDER BY p.code) AS perms
  FROM role_permissions rp
  JOIN roles       r ON r.id = rp.role_id
  JOIN permissions p ON p.id = rp.permission_id
 GROUP BY r.code
 ORDER BY r.code;

-- 4.3 ★ 最关键的一行：这七列【必须】是
--        3 / 2 / 5 / 2 / 4 / 1 / 0
--     左一：user 权限总数 = 3（user:list 是旧有的，detail/status 是本日新增）
--     左二：dashboard 权限总数 = 2
--     左三：role 1（SUPER_ADMIN）拿到的 user+dashboard 权限数 = 5（全部 = 3 + 2）
--     左四：role 2（PRODUCT_ADMIN）拿到的 = 2（只有 dashboard:*）★ 反向对照
--     左五：role 3（ORDER_ADMIN）拿到的 = 4（dashboard:2 + user:list + user:detail）
--           ★ 首次落地时这一格被写成 3，脚本当场报 FAIL —— 数据是对的，
--             错的是这条心算。⇒ 凡「合计」类期望值，都要能从别的格子复算出来
--             （左五 = 左二 + user:list + user:detail = 2 + 1 + 1），别凭印象填。
--     左六：role 3 拿到的 user:detail 数 = 1（读买家信息是订单岗位的活）
--     左七：role 3 拿到的 user:status 数 = 0 ★★ 期望就是 0（禁用只给超管）
--     ⚠️ 若左三 < 5 ⇒ @PreAuthorize 会稳定 403；若左七 > 0 ⇒ 权限给多了。
SELECT (SELECT count(*) FROM permissions WHERE code LIKE 'user:%')                      AS user_perms_total,
       (SELECT count(*) FROM permissions WHERE code LIKE 'dashboard:%')                 AS dashboard_perms_total,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 1 AND (p.code LIKE 'user:%' OR p.code LIKE 'dashboard:%'))  AS role1_ud,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 2 AND (p.code LIKE 'user:%' OR p.code LIKE 'dashboard:%'))  AS role2_ud,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 3 AND (p.code LIKE 'user:%' OR p.code LIKE 'dashboard:%'))  AS role3_ud,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 3 AND p.code = 'user:detail')                               AS r3_user_detail,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 3 AND p.code = 'user:status')                               AS r3_user_status;

-- 4.4 权限总数（应 = 25）
SELECT count(*) AS permissions_total, max(id) AS max_id FROM permissions;
