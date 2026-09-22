-- ============================================================
-- MallX 权限补发（Day 17）—— 管理端订单 + 库存管理
-- 说明：需在 01-schema.sql、02-index.sql、03-data.sql 之后执行。
--       幂等：可重复执行；只【增】不【改】历史种子（03-data.sql 一个字都不动）。
-- ============================================================
--
-- ★★ 为什么必须有这个文件（本文件的全部存在理由）：
--
--   03-data.sql 里的授权用的是「按 code 前缀批量授」的写法：
--
--       INSERT INTO role_permissions (role_id, permission_id)
--       SELECT 3, p.id FROM permissions p
--       WHERE p.code LIKE 'order:%'          -- ORDER_ADMIN
--
--   它【只在首次种子时执行过一次】。今天新增 order:detail / inventory:* 时，
--   那条 LIKE 不会再跑 —— 于是新权限行进了 permissions 表，
--   但 role_permissions 里【没有任何一行】指向它们
--   → @PreAuthorize("hasAuthority('inventory:adjust')") 永远 403。
--
--   ★ 这个失败模式很坏：它看起来像「代码写错了」（注解拼错？权限码拼错？），
--     实际是【数据没补】—— 排查方向天然会跑到 Java 那边去。
--   ★ 对照 Day 16 的教训：缺 UNIQUE 是「当场报错」，缺 NOT NULL 是「错得安静」。
--     这里同样属于「错得安静」那一类：没有任何日志、没有任何异常，只有一个稳定的 403。
-- ============================================================

-- ------------------------------------------------------------
-- 一、订正 order:list 的 path
-- ------------------------------------------------------------
-- 03-data.sql 里它是 '/api/orders' GET —— 指向的是【C 端】端点，是个无效指向：
--   C 端列表压根不查权限码（它挂的是 anyRequest().authenticated()，登录即可）。
-- 管理端列表（本日新增）的真实路径是 GET /api/admin/orders。
--
-- ★ 为什么加 AND path = '/api/orders'：
--   ① 幂等 —— 第二次执行时它已经等于新值，条件不成立 → 0 行，
--      不会把 updated_at 反复刷新（伪幂等会让「谁在什么时候改过」这条线索失效）；
--   ② 只改「还停在旧值」的那一行 —— 万一有人已经手动订正过，本语句不覆盖他的值。
UPDATE permissions
   SET path       = '/api/admin/orders',
       updated_at = CURRENT_TIMESTAMP
 WHERE code = 'order:list'
   AND path = '/api/orders';

-- ------------------------------------------------------------
-- 二、新增 5 条管理端权限
-- ------------------------------------------------------------
-- id 9..13：接在 03-data.sql 的 1..8 之后（那边八条全是显式 id）。
-- path 的 * 是通配风格，与 03-data.sql 的 '/api/products/*' 保持一致。
-- ⚠️ path 这一列在本项目【当前还没有任何代码在读】—— 它只是权限的「人类可读定位信息」，
--    真正的把门人是 Java 侧的 @PreAuthorize 权限码。所以 path 写错不会导致故障，
--    但会让后来者按 path 去找端点时找错地方（本文件第一步订正的正是这类历史遗留）。
INSERT INTO permissions (id, name, code, type, path, method)
SELECT v.id, v.name, v.code, v.type, v.path, v.method
FROM (VALUES
    (9,  '管理端订单详情', 'order:detail',     'API', '/api/admin/orders/*',              'GET'),
    (10, '管理端取消订单', 'order:cancel',     'API', '/api/admin/orders/*/cancel',       'POST'),
    (11, '库存列表',       'inventory:list',   'API', '/api/admin/inventory/skus',        'GET'),
    (12, '调整库存',       'inventory:adjust', 'API', '/api/admin/inventory/skus/*/adjust','POST'),
    (13, '库存流水',       'inventory:log',    'API', '/api/admin/inventory/logs',        'GET')
) AS v(id, name, code, type, path, method)
WHERE NOT EXISTS (SELECT 1 FROM permissions p WHERE p.code = v.code);

-- ★ 存在性判断用【code】而不是 id：code 上有 UNIQUE 约束（01-schema.sql:341），
--   而 id 只是个约定值。用 code 判断，即使将来有人手工挪过 id，本语句依然幂等。
-- ⚠️ 反过来说：显式指定 id 的种子【必须】校准序列（见第四节），
--   否则业务侧后续 INSERT 会撞主键（03-data.sql 末尾那段注释讲的就是这件事）。

-- ------------------------------------------------------------
-- 二·续、订正 order:detail 的名称与路径（Day 17 收尾追加）
-- ------------------------------------------------------------
-- 上一段的 INSERT 只对【新库】生效（NOT EXISTS 挡着）。对已经落过库的环境，
-- 第 9 行早就存在了，于是那处笔误被固定了下来：
--
--   code = 'order:detail'      ← 权限码是对的（@PreAuthorize 认的正是它）
--   name = '管理端订单列表'      ← 错的：这是 id=6（order:list）的名字，照抄时没改
--   path = '/api/admin/orders' ← 错的：同上，这是【列表】的路径
--
-- ★ 危害等级：低 —— path 这一列当前没有任何代码在读，纯粹是「人类可读定位信息」。
--   但它的危害方式恰恰是最贵的那一种：后来者按 path 去搜「详情端点在哪」，
--   搜到 /api/admin/orders，然后看见列表的实现，然后开始怀疑是自己找错了地方。
--   ★ 这与本节第一部分订正 order:list path 是同一个理由 —— 说明「注释/元数据里的
--     错误指向」在本项目里已经出现过两次，属于需要主动巡检的那一类问题。
--
-- ⚠️ 守卫为什么写 AND name = ... 而不是 AND path = ...：
--   「哪一处是笔误」要靠【name 与 code 的矛盾】判断 —— name 说这是列表、code 说这是详情，
--   两者必有一错。以 code 为准（它才是把门人），所以本语句只改「还停在旧 name」的那一行；
--   若有人已经手工订正过，这里不覆盖他的值。
UPDATE permissions
   SET name       = '管理端订单详情',
       path       = '/api/admin/orders/*',
       updated_at = CURRENT_TIMESTAMP
 WHERE code = 'order:detail'
   AND name = '管理端订单列表';

-- ------------------------------------------------------------
-- 三、补发授权（★ 本文件的核心动作）
-- ------------------------------------------------------------
-- 三条 INSERT 的形状与 03-data.sql 完全一致（SELECT + NOT EXISTS 双保险），
-- 这样「新授权的写法」与「历史授权的写法」是同一个胚子，不会分叉。

-- ① 超级管理员（role 1）：拿【全部】权限 —— 不限前缀，
--    因为它要的语义就是「以后新增的权限也归我」。
INSERT INTO role_permissions (role_id, permission_id)
SELECT 1, p.id
FROM permissions p
WHERE NOT EXISTS (SELECT 1 FROM role_permissions rp
                   WHERE rp.role_id = 1 AND rp.permission_id = p.id);

-- ② 订单管理员（role 3 / ORDER_ADMIN）：拿所有 order:*
--    ★ 这一次它才真正拿到 order:detail / order:cancel ——
--      03-data.sql 那次 LIKE 只覆盖到当时存在的 order:list / order:ship。
INSERT INTO role_permissions (role_id, permission_id)
SELECT 3, p.id
FROM permissions p
WHERE p.code LIKE 'order:%'
  AND NOT EXISTS (SELECT 1 FROM role_permissions rp
                   WHERE rp.role_id = 3 AND rp.permission_id = p.id);

-- ③ 商品管理员（role 2 / PRODUCT_ADMIN）：拿所有 inventory:*
--    ★ 库存权限【故意不给 ORDER_ADMIN】—— 这正是本日验收里
--      「op_order 账号订单端点 200、库存端点 403」那组断言的依据：
--      含混地让订单管理员也能改库存，权限矩阵就没有区分度了。
INSERT INTO role_permissions (role_id, permission_id)
SELECT 2, p.id
FROM permissions p
WHERE p.code LIKE 'inventory:%'
  AND NOT EXISTS (SELECT 1 FROM role_permissions rp
                   WHERE rp.role_id = 2 AND rp.permission_id = p.id);

-- ------------------------------------------------------------
-- 四、序列校准（★ 与 03-data.sql 末尾同一件事）
-- ------------------------------------------------------------
-- 上面用显式 id 插入了 9..13，PG 的序列不会因此前进 → 必须推到 MAX(id)。
-- 漏了它的现象：业务侧下一次 INSERT 拿到 nextval=1，撞上已存在的 id → 23505。
SELECT setval(pg_get_serial_sequence('permissions', 'id'),
              COALESCE((SELECT MAX(id) FROM permissions), 1));

-- ------------------------------------------------------------
-- 五、自检（执行后请人工核对这三段输出）
-- ------------------------------------------------------------
-- 5.1 五条新权限是否都在，且 order:list 的 path 是否已订正
SELECT id, code, name, path, method
  FROM permissions
 WHERE code LIKE 'order:%' OR code LIKE 'inventory:%'
 ORDER BY id;

-- 5.2 谁拿到了什么（★ 期望：role 1 = 13 条；role 2 含 3 条 inventory:*；role 3 含 4 条 order:*）
SELECT r.code AS role_code,
       count(*)                                          AS perm_count,
       string_agg(p.code, ', ' ORDER BY p.code)           AS perms
  FROM role_permissions rp
  JOIN roles       r ON r.id = rp.role_id
  JOIN permissions p ON p.id = rp.permission_id
 GROUP BY r.code
 ORDER BY r.code;

-- 5.3 ★ 最关键的一行：这三条计数【必须相等】，否则 @PreAuthorize 会稳定 403
--     （左：库存权限总数 3；中：role 2 拿到的库存权限数 3；右：role 1 拿到的库存权限数 3）
--     ⚠️ 是 3 不是 4 —— inventory:list / inventory:adjust / inventory:log 共三条。
--        本注释最初写成 4，实测后订正（一个写错的目标值比没有目标值更坏：
--        它会让核对的人以为自己少发了一条权限，转而去改【正确】的授权语句）。
SELECT (SELECT count(*) FROM permissions p WHERE p.code LIKE 'inventory:%')                 AS inventory_perms_total,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 2 AND p.code LIKE 'inventory:%')                                AS granted_to_product_admin,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 1 AND p.code LIKE 'inventory:%')                                AS granted_to_super_admin,
       (SELECT count(*) FROM permissions p WHERE p.code LIKE 'order:%')                     AS order_perms_total,
       (SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = 3 AND p.code LIKE 'order:%')                                    AS granted_to_order_admin;
