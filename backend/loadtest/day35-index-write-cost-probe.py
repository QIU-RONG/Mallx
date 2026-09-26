# -*- coding: utf-8 -*-
"""Day 35 · 把「写入成本」量出来 —— 我用了五天的判据，从来没测过。

为什么需要它
------------
从 Day 29 起，我删索引的理由一直是这一句：

    「不值一份写入成本」

Day 29（payments）、Day 30（该不该删看写入成本）、Day 32（分页复合索引）、
Day 33/34（冗余索引）—— **这句话我用了 5 次，却从来没测过它到底值多少。**

★★ 这正是本项目反复现形的那类错误：**拿一个没取证的前提当判据**。
   （同族：Day 27 的「记忆里的缺口 ≠ 代码里的缺口」、Day 20 的「照着实现写断言」。）
   如果「一份写入成本」其实小到可忽略，那我前面几天的结论**理由部分就是错的** ——
   结论可能还对，但**理由必须换一个**。

做法（★ 零副作用）
------------------
临时库 `mallx_write_probe`。对 4 张表各做两轮**单行 INSERT**（走 plpgsql 循环，
贴近 MyBatis 的真实写法，不是 `COPY`），每轮 5000 行，用 Python 墙钟计时：

    阶段 A：索引都在
    阶段 B：把候选索引 DROP 掉，同样的插入再来一遍
    对比：省了多少

★★ 对照组：光测「候选索引」不够 —— 如果省了 0.3%，我怎么知道**是索引真的不贵**，
   还是**我这个装置测不出写入成本**？
   ⇒ 所以额外做一组对照：`products` 保留全部索引 vs **全部 DROP**。
   它**必须**有显著差异，否则本装置不可信。

运行：python day35-index-write-cost-probe.py
前置：容器 mallx-postgres 在运行（**不需要**应用在跑）。
"""
from _paths import lp
import os
import re
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DOCKER = os.environ.get("MALLX_DOCKER") or r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
CONTAINER = "mallx-postgres"
DB_USER = "mallx"
ADMIN_DB = "mallx"
PROBE_DB = "mallx_write_probe"
SQL_DIR = lp(r"D:\MallX\backend\sql")
REPORT = lp(r"D:\MallX\backend\loadtest\day35-index-write-cost-probe-report.txt")

FILES = ["01-schema.sql", "02-index.sql", "03-data.sql", "04-review-constraints.sql",
         "05-admin-permissions.sql", "06-day17-fixtures.sql", "07-admin-permissions.sql",
         "08-marketing-permissions.sql", "09-user-coupons-unique.sql",
         "10-brand-permissions.sql", "11-order-discount.sql", "12-day22-permissions.sql",
         "13-day23-permissions.sql", "14-brand-crud-permissions.sql",
         "15-search-trgm-indexes.sql"]

N_ROWS = 5000          # 每轮插入行数
N_USERS = 2000
N_CATEGORIES = 300
N_PRODUCTS = 20000

EXPECTED_CHECKS = 19

lines = []
say = lines.append
n_pass = n_fail = 0
RES = {}   # label -> dict(a=秒, b=秒, dropped=[...], kept=[...])


def chk(name, ok, detail=""):
    global n_pass, n_fail
    if ok:
        n_pass += 1
        say("  [OK]   %s%s" % (name, ("   " + detail) if detail else ""))
    else:
        n_fail += 1
        say("  [FAIL] %s   %s" % (name, detail))
    return ok


def psql(db, sql_text, stop=True, timeout=1800):
    args = [DOCKER, "exec", "-i", "-e", "PGCLIENTENCODING=UTF8",
            CONTAINER, "psql", "-U", DB_USER, "-d", db]
    if stop:
        args += ["-v", "ON_ERROR_STOP=1"]
    args += ["-t", "-A", "-F", "|"]
    p = subprocess.run(args, input=sql_text, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return (p.returncode,
            (p.stdout or "").replace("\r", "").strip(),
            (p.stderr or "").replace("\r", "").strip())


def one(sql):
    rc, out, err = psql(PROBE_DB, sql)
    if rc != 0:
        raise RuntimeError("SQL 失败 rc=%d err=%s\n%s" % (rc, err[:300], sql[:200]))
    return out.splitlines()[0] if out else ""


def timed_insert(label, insert_sql, n, base=0):
    """跑 n 次单行 INSERT（plpgsql 循环，i ∈ [base+1, base+n]），返回墙钟秒数。
    base 的作用：阶段 B 平移 i，避开唯一约束下与阶段 A 相同的取值组合。"""
    body = ("DO $$\nBEGIN\n  FOR i IN %d + 1 .. %d + %d LOOP\n    %s\n  END LOOP;\nEND $$;\n"
            % (base, base, n, insert_sql))
    t0 = time.time()
    rc, out, err = psql(PROBE_DB, body)
    dt = time.time() - t0
    if rc != 0:
        raise RuntimeError("[%s] 插入失败 rc=%d err=%s" % (label, rc, err[:300]))
    return dt


# ------------------------------------------------------------------ 造数（基础数据，不含待插入的行）
SEEDS = [
    ("维表 %d 用户" % N_USERS, """
INSERT INTO users (username, password, nickname, phone, email, status)
SELECT 'perfuser' || g, 'x', 'PERF', '139' || lpad(g::text, 8, '0'),
       'perf' || g || '@example.com', 1
FROM generate_series(1, %d) g;
""" % N_USERS),

    ("维表 %d 分类" % N_CATEGORIES, """
INSERT INTO categories (parent_id, name, sort_order, status)
SELECT NULL, 'PERF-分类-' || g, 0, 1 FROM generate_series(1, %d) g;
""" % N_CATEGORIES),

    ("商品 %d + SKU x2" % N_PRODUCTS, """
INSERT INTO products (category_id, brand_id, name, subtitle, description, main_image, status, is_deleted)
SELECT (SELECT id FROM categories ORDER BY id OFFSET (g %% (SELECT count(*) FROM categories)) LIMIT 1),
       (SELECT id FROM brands ORDER BY id OFFSET (g %% GREATEST((SELECT count(*) FROM brands),1)) LIMIT 1),
       'PERF-商品-' || g, 'PERF-副标题', 'PERF-描述', '/img/perf-' || g || '.jpg', 1, 0
FROM generate_series(1, %d) g;

INSERT INTO product_skus (product_id, sku_code, name, price, original_price, attributes, image, status, is_deleted)
SELECT p.id, 'PERF-SKU-' || p.id, 'PERF-SKU', 100.00, 200.00,
       jsonb_build_object('color', '白色'), '/img/perf-sku.jpg', 1, 0
FROM products p WHERE p.name LIKE 'PERF-%%';

INSERT INTO coupons (name, type, discount_amount, min_amount, total_count, received_count, start_time, end_time, status)
SELECT 'PERF-券-' || g, 'DISCOUNT', 10.00, 100.00, 1000, 0,
       CURRENT_TIMESTAMP - interval '10 days', CURRENT_TIMESTAMP + interval '10 days', 1
FROM generate_series(1, 250) g;
""" % N_PRODUCTS),

    ("订单占位（order_items 需要 order_id）", """
INSERT INTO orders (order_no, user_id, total_amount, pay_amount, status,
                    receiver_name, receiver_phone, receiver_address, created_at, updated_at)
SELECT 'PERF-ORD-' || g, (SELECT id FROM users ORDER BY id LIMIT 1),
       100.00, 100.00, 'PAID', 'PERF', '13000000000', 'PERF 地址',
       CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM generate_series(1, %d) g;
""" % N_ROWS),
]

# ------------------------------------------------------------------ 4 组实验
# (标签, 说明, 目标表, 插入语句, 候选索引[DROP], 对照保留索引)
#
# ★ 取值规则（全部走「取模在表内取已有 id」，两阶段复用同一套 i）：
#   - schema 硬约束：cart_items.sku_id / user_coupons.user_id 均 NOT NULL + FK
#     ⇒ 绝不能用「OFFSET 超出表行数」的写法（取到 NULL 直接炸）。
#   - 唯一约束 uk_*（user_id, sku_id / user_id, coupon_id）⇒ 两阶段不能重放同样的组合：
#     timed_insert 给阶段 B 加 base=N_ROWS（i 整体平移 5000），组合天然错开；
#     组内碰撞需要 |Δi| 同时是 users 行数和另一取值周期的公倍数（≥ 数万），
#     而 |Δi| ≤ 9999 ⇒ 不可能；优惠券偏移特意用质数 211（种子 250 个）避开 users 行数的整除周期。
#   - order_items / products.name 无唯一约束。
CASES = [
    ("order_items", "订单明细（下单链路的热写点）", "order_items",
     "INSERT INTO order_items (order_id, product_id, sku_id, product_name, sku_name, price, quantity, total_amount, image) "
     "VALUES ((SELECT min(id) FROM orders), (SELECT min(id) FROM products), "
     "        (SELECT min(id) FROM product_skus), 'PERF', 'PERF', 100.00, 1, 100.00, '/img/x.jpg');",
     ["idx_order_items_sku_id"], ["idx_order_items_order_id"]),

    ("cart_items", "购物车（每次加购都写）", "cart_items",
     "INSERT INTO cart_items (user_id, sku_id, quantity, selected) "
     "VALUES ((SELECT id FROM users ORDER BY id OFFSET (i % (SELECT count(*) FROM users)) LIMIT 1), "
     "        (SELECT id FROM product_skus ORDER BY id OFFSET (i % (SELECT count(*) FROM product_skus)) LIMIT 1), 1, TRUE);",
     ["idx_cart_items_user_id", "idx_cart_items_sku_id"], ["uk_cart_user_sku"]),

    ("user_coupons", "领券（唯一约束索引必须留）", "user_coupons",
     "INSERT INTO user_coupons (user_id, coupon_id, status) "
     "VALUES ((SELECT id FROM users ORDER BY id OFFSET (i % (SELECT count(*) FROM users)) LIMIT 1), "
     "        (SELECT id FROM coupons ORDER BY id OFFSET (i % 211) LIMIT 1), 'UNUSED');",
     ["idx_user_coupons_user_id", "idx_user_coupons_coupon_id"], ["uk_user_coupons_user_coupon"]),

    # ★★ 对照：把 products 的**全部索引**都 DROP 掉 —— 它必须出现显著差异，
    #    否则说明本装置根本测不出写入成本，前面的「省了 x%」全都不可信。
    ("products(对照)", "对照：全部索引 vs 无索引", "products",
     "INSERT INTO products (category_id, brand_id, name, subtitle, description, main_image, status, is_deleted) "
     "VALUES ((SELECT min(id) FROM categories), (SELECT min(id) FROM brands), "
     "        'PERF-W-' || i, 'PERF', 'PERF', '/img/x.jpg', 1, 0);",
     ["idx_products_category_id", "idx_products_brand_id", "idx_products_status",
      "idx_products_is_deleted", "idx_products_search", "idx_products_name_trgm",
      "idx_products_subtitle_trgm", "idx_products_description_trgm"],
     []),
]


def main():
    say("=" * 78)
    say("Day 35 -- 把「写入成本」量出来（每轮单行 INSERT x %d）" % N_ROWS)
    say("=" * 78)

    say("")
    say("[0] 建临时库（★ 只动这一个名字，开发库不碰）")
    rc, _o, err = psql(ADMIN_DB, "DROP DATABASE IF EXISTS %s;\nCREATE DATABASE %s;" % (PROBE_DB, PROBE_DB))
    chk("CREATE DATABASE %s" % PROBE_DB, rc == 0, "rc=%d err=%s" % (rc, err[:160]))
    if rc != 0:
        return bail()

    try:
        say("")
        say("[1] 按序灌 01→14")
        bad = []
        for name in FILES:
            rc, _o, err = psql(PROBE_DB, open(os.path.join(SQL_DIR, name), encoding="utf-8").read())
            if rc != 0:
                bad.append(name)
                say("      [FAIL] %s   %s" % (name, err.replace("\n", " | ")[:200]))
        chk("14 份补丁全部 rc == 0", not bad, "bad=%s" % bad)
        if bad:
            return bail()

        say("")
        say("[2] 造基础数据")
        for label, sql in SEEDS:
            rc, _o, err = psql(PROBE_DB, sql)
            chk("造数 %s" % label, rc == 0, "rc=%d err=%s" % (rc, err[:200]))

        say("")
        say("[3] VACUUM (ANALYZE)")
        rc, _o, err = psql(PROBE_DB, "VACUUM (ANALYZE);")
        chk("基线 VACUUM (ANALYZE)", rc == 0, "err=%s" % err[:160])

        say("")
        say("[4] ★★ 阶段 A —— 索引都在，逐表插入 %d 行" % N_ROWS)
        for label, desc, tbl, ins, drop_list, keep in CASES:
            before = int(one("SELECT count(*) FROM %s" % tbl))
            dt = timed_insert(label, ins, N_ROWS, base=0)
            after = int(one("SELECT count(*) FROM %s" % tbl))
            RES[label] = dict(a=dt, a_rows=after - before, b=None, b_rows=None,
                              drop=drop_list, keep=keep, desc=desc, tbl=tbl)
            say("      %-16s %7.3fs  (%.3f ms/行)  新增 %d 行  %s"
                % (label, dt, dt * 1000.0 / N_ROWS, after - before, desc))

        say("")
        say("[5] 阶段 B —— DROP 候选索引 + VACUUM (ANALYZE)")
        all_drop = sorted({n for _l, _d, _t, _i, dl, _k in CASES for n in dl})
        rc, _o, err = psql(PROBE_DB, "".join("DROP INDEX IF EXISTS %s;\n" % n for n in all_drop))
        chk("DROP 候选索引（%d 个）" % len(all_drop), rc == 0, "rc=%d err=%s" % (rc, err[:200]))
        rc, _o, err = psql(PROBE_DB, "VACUUM (ANALYZE);")
        chk("DROP 后 VACUUM (ANALYZE)", rc == 0, "err=%s" % err[:160])

        say("")
        say("[6] 阶段 B —— 同样插入 %d 行" % N_ROWS)
        for label, desc, tbl, ins, drop_list, keep in CASES:
            before = int(one("SELECT count(*) FROM %s" % tbl))
            dt = timed_insert(label, ins, N_ROWS, base=N_ROWS)
            after = int(one("SELECT count(*) FROM %s" % tbl))
            RES[label]["b"] = dt
            RES[label]["b_rows"] = after - before
            say("      %-16s %7.3fs  (%.3f ms/行)  新增 %d 行"
                % (label, dt, dt * 1000.0 / N_ROWS, after - before))

        say("")
        say("[7] ★ 数据完整性：两轮都插够了行数（否则计时没有可比性）")
        for label, desc, tbl, ins, drop_list, keep in CASES:
            r = RES[label]
            chk("%s 阶段 A 新增 == %d" % (label, N_ROWS), r["a_rows"] == N_ROWS,
                "actual=%d" % r["a_rows"])
            chk("%s 阶段 B 新增 == %d" % (label, N_ROWS), r["b_rows"] == N_ROWS,
                "actual=%d" % r["b_rows"])

        say("")
        say("[8] ★★ 对照组必须成立：products 全部索引 vs 无索引，差异要显著")
        ctl = RES["products(对照)"]
        gain = (ctl["a"] - ctl["b"]) / ctl["a"] * 100.0
        say("      全索引 %.3fs → 无索引 %.3fs  ⇒ 省 %.1f%%" % (ctl["a"], ctl["b"], gain))
        chk("对照组差异 >= 10%%（证明本装置能测出写入成本）", gain >= 10.0,
            "gain=%.1f%%" % gain)

    finally:
        say("")
        say("[9] 删临时库")
        rc, _o, err = psql(ADMIN_DB, "DROP DATABASE IF EXISTS %s;" % PROBE_DB)
        chk("DROP DATABASE %s" % PROBE_DB, rc == 0, "rc=%d err=%s" % (rc, err[:160]))

    return bail()


def bail(code=None):
    say("")
    say("=" * 78)
    say("写入成本对照表（每轮 %d 行单行 INSERT）" % N_ROWS)
    say("=" * 78)
    say("      %-16s %-10s %-10s %-8s %s" % ("表", "A 全索引", "B 去候选", "省", "DROP 掉的索引"))
    for label, desc, tbl, ins, drop_list, keep in CASES:
        r = RES.get(label)
        if not r or r["b"] is None:
            continue
        gain = (r["a"] - r["b"]) / r["a"] * 100.0
        say("      %-16s %-10s %-10s %-8s %s" % (
            label, "%.3fs" % r["a"], "%.3fs" % r["b"], "%.1f%%" % gain, ",".join(r["drop"])))

    total = n_pass + n_fail
    say("")
    say("=" * 78)
    say("ASSERTIONS: %d / %d passed   (EXPECTED=%d)" % (n_pass, total, EXPECTED_CHECKS))
    full = (total == EXPECTED_CHECKS)
    if not full:
        say("★ 满额护栏未过：实得 %d 条断言，期望 %d 条 ⇒ 有检查项根本没被执行到"
            % (total, EXPECTED_CHECKS))
    ok = (n_fail == 0) and full
    say("VERDICT: %s" % ("OK -- 写入成本已量化，且对照组证明装置可信" if ok
                         else "FAIL -- 见上面 FAIL 行"))
    say("=" * 78)
    with open(REPORT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print("report -> %s" % REPORT)
    if code is None:
        code = 0 if ok else 1
    return code


if __name__ == "__main__":
    sys.exit(main())
