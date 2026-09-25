-- ============================================================
-- MallX DDL 补丁（Day 20）—— user_coupons 的「一人一券」唯一约束
-- 说明：需在 01-schema / 02-index / 03-data 之后执行。幂等，可重复执行。
-- ============================================================
--
-- ★★ 为什么需要它：
--   01-schema.sql 建的 user_coupons 只有 2 个外键 + 1 个主键，【没有任何唯一约束】
--   → 「同一个用户重复领同一张券」在数据库层面完全合法 → 靠应用层 SELECT 挡 = TOCTOU。
--   有了它，领取那条 INSERT ... ON CONFLICT (user_id, coupon_id) DO NOTHING 才有牙齿
--   （没有约束时这条语句【直接报错】，不是静默降级）。
--
-- ★★★ 顺序不能死记 —— 先体检，再照抄：
--
--   Day 16 给 reviews 加唯一约束时，目标列 order_item_id 是【可空】的，所以
--   必须先 SET NOT NULL 再加 UNIQUE（PG 的 UNIQUE 豁免 NULL，两行 NULL 互不相等
--   → 唯一约束被整条绕过，而且【错得安静、不报错】）。
--
--   本表【不用】那一步：user_id 与 coupon_id 建表时就是 NOT NULL。
--   ⇒ 第一节先把这个前提【查出来看】，而不是假设它成立。
--      换一张表、换一台机器，前提就可能不成立。
-- ============================================================

-- ------------------------------------------------------------
-- 一、前提体检（★ 必须先看这两段输出）
-- ------------------------------------------------------------

-- 1.1 两列的可空性：★ 期望都是 NO（is_nullable = 'NO'）。
--     若出现 YES → 先执行（并把存量数据补齐）：
--         ALTER TABLE user_coupons ALTER COLUMN user_id   SET NOT NULL;
--         ALTER TABLE user_coupons ALTER COLUMN coupon_id SET NOT NULL;
--     否则下面的 UNIQUE 会被 NULL 行绕过。
SELECT column_name, is_nullable, data_type
  FROM information_schema.columns
 WHERE table_name = 'user_coupons'
   AND column_name IN ('user_id', 'coupon_id')
 ORDER BY column_name;

-- 1.2 存量重复体检：★ 期望 0 行。
--     ⚠️ 若这里查出数据，【不要】直接删 —— 先把这份清单给人看：
--        重复的券哪一张已用（status='USED' 或 order_id 非空）、哪一张没用，
--        决定保留哪一行是业务判断，脚本无权替人决定。
--     （本日这张表是空的，所以必然 0 行；但换台有数据的机器就不是了 → 写进来。）
SELECT user_id, coupon_id, count(*) AS dup_rows
  FROM user_coupons
 GROUP BY user_id, coupon_id
HAVING count(*) > 1
 ORDER BY dup_rows DESC, user_id, coupon_id;

-- ------------------------------------------------------------
-- 二、加唯一约束（幂等）
-- ------------------------------------------------------------
-- 用 DO 块 + pg_constraint 判断，重复执行不会报 "already exists"。
-- ★ 约束名必须显式给（uk_user_coupons_user_coupon）——
--   靠 PG 自动起名（user_coupons_user_id_coupon_id_key）会让「按名字查是否存在」失效。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uk_user_coupons_user_coupon'
    ) THEN
        ALTER TABLE user_coupons
          ADD CONSTRAINT uk_user_coupons_user_coupon UNIQUE (user_id, coupon_id);
    END IF;
END $$;

-- ★ 加约束会【上锁并扫描全表】校验存量数据；本表为空（或有索引可用）所以瞬间完成。
--   在真实的大表上这一步要单独择时执行 —— 这也是「补丁脚本要和业务代码分开跑」的理由之一。

-- ------------------------------------------------------------
-- 三、自检（执行后请人工核对这三段输出）
-- ------------------------------------------------------------

-- 3.1 约束是否在：★ 期望 1 行，contype = 'u'
SELECT conname, contype, pg_get_constraintdef(oid) AS definition
  FROM pg_constraint
 WHERE conname = 'uk_user_coupons_user_coupon';

-- 3.2 索引是否随之建立（UNIQUE 约束背后就是一个唯一索引）
SELECT indexname, indexdef
  FROM pg_indexes
 WHERE tablename = 'user_coupons'
 ORDER BY indexname;
-- ★ 期望看到 4 个：pk_user_coupons、uk_user_coupons_user_coupon，
--   外加 02-index.sql 建的 idx_user_coupons_user_id / idx_user_coupons_coupon_id。

-- 3.3 ★ 功能验证（零痕迹：整段包在事务里，最后 ROLLBACK）
--     证明约束真的在拦重复 —— 不然「约束存在」只是元数据上的事实。
--
-- ⚠️★★ 这一段一共踩过两个坑，两个都必须写下来：
--
--   坑 ①（第一次写）：直接插两次 user_coupons(1, 1)，期望第二次撞【唯一约束】。
--     实测撞的是【外键约束】，因为 coupons 表是空的、coupon_id=1 根本不存在：
--         ERROR: insert or update on table "user_coupons" violates
--                foreign key constraint "fk_user_coupon_coupon"
--     外键先于唯一约束暴露 ⇒ 这条「功能验证」什么都没验到，
--     而且它【看起来是绿的】（确实报错了嘛）—— 比不写还坏。
--     ⇒ 要验唯一约束，必须先把数据摆成「所有外键都满足」的状态：先造一张券。
--     ★ 这与 Day 19 的教训同源：探针的【前提】必须先建好，否则测的不是你以为的东西。
--
--   坑 ②（第二次写，即本次）：把「期望抛错」原样交给 psql 执行。
--     在【交互式 psql】里看不出问题；但同一个文件被 `psql -v ON_ERROR_STOP=1` 批处理时
--     （★ 正是 `docker-entrypoint-initdb.d` 的执行方式），这条【故意的】错误会
--     直接掐断整个初始化 —— 后面的 10/11/12/13/14 号补丁【全部静默跳过】。
--     实测现场：容器内 permissions 只有 20 行（应为 41）、品牌 CRUD 的 39/40/41 缺失，
--     而 initdb 日志里只有一句 FATAL，粗看像「基础镜像拉不下来」之类的问题，排查方向整个跑偏。
--     ⇒ 修法：把「期望失败」的那条 INSERT 包进 plpgsql 的 EXCEPTION 块 ——
--        让异常在【数据库内部】被接住、翻译成 NOTICE，psql 看到的退出码是 0。
--        既保住了验证，又不再打断批处理。
--     ★ 一般化：一个 SQL 文件要同时满足「交互跑」与「批处理跑」两种用法时，
--       「故意报错」必须被内部消化，绝不能漏到 psql 层。
--     ★ 同源推论：验证要能被【自动判定】（退出码 / 断言），而不是靠人去读 stderr 里
--       那句话长得对不对 —— 靠人看的那一步，换个环境就没人看了。
BEGIN;
    -- ① 先造一张临时券（id 挑一个不会被真实数据占用的值；ROLLBACK 后不留痕）
    INSERT INTO coupons (id, name, type, discount_amount, total_count,
                         start_time, end_time, status)
    VALUES (999999, 'tmp-constraint-check', 'FIXED', 1.00, 1,
            '2020-01-01 00:00:00', '2030-01-01 00:00:00', 1);

    -- ② 领一次：应当成功（user_id=1 是种子用户 demo）
    INSERT INTO user_coupons (user_id, coupon_id) VALUES (1, 999999);

    DO $$
    DECLARE
        v_rejected boolean := false;
        v_err      text;
    BEGIN
        BEGIN
            -- ③ 再领一次：★ 这一行【期望】抛错 ——
            --      duplicate key value violates unique constraint "uk_user_coupons_user_coupon"
            --    ★ 关键：它在子块里被接住，不外泄给 psql。
            --      子块回滚后，①② 的插入仍在，交给最后的 ROLLBACK 收拾。
            INSERT INTO user_coupons (user_id, coupon_id) VALUES (1, 999999);
        EXCEPTION
            WHEN unique_violation THEN
                v_rejected := true;
                v_err := SQLERRM;
            WHEN others THEN
                -- 撞到别的错（最典型是外键）⇒ 探针的【前提】没建好，这次验证无效。
                -- ★ 大声失败：绝不让「无效的验证」长得像绿的（坑 ① 的教训）。
                RAISE EXCEPTION
                    'SELF-CHECK INVALID：期望唯一约束冲突，实得 SQLSTATE %（%）⇒ 探针前提没建好，本次验证无效',
                    SQLSTATE, SQLERRM;
        END;

        IF NOT v_rejected THEN
            RAISE EXCEPTION
                'SELF-CHECK FAILED：重复领取【被接受】了 ⇒ uk_user_coupons_user_coupon 没有起作用';
        END IF;

        RAISE NOTICE 'SELF-CHECK OK：重复领取已被唯一约束拒绝（%）', v_err;
    END $$;
ROLLBACK;
-- ★ 判据（已从「人看 stderr」改为「看退出码」）：
--     · 退出码 0，且输出里出现 NOTICE「SELF-CHECK OK」 ⇒ 约束在拦，验证通过；
--     · 退出码非 0                                     ⇒ 约束没起作用（或探针前提没建好），必须查。
--   ★ 零痕迹证明：③ 的尝试由 plpgsql 子块回滚；① ② 由最后的 ROLLBACK 回滚。
--     可复核：`select count(*) from coupons where id = 999999;` 恒为 0。
