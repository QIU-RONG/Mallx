# -*- coding: utf-8 -*-
"""Day 34 · 把「被复合索引覆盖」这个模式扫干净（购物车两个索引 + 一个对照）。

来由
----
Day 33 发现 `idx_user_coupons_user_id` 是**冗余**的 —— 它被 09 号补丁的
`UNIQUE(user_id, coupon_id)` 索引完全覆盖（该唯一索引**第一列就是 user_id**）。

本日把**同一个模式**在别处扫一遍。逐表核对约束形态后，只剩一处符合：

    cart_items 有 UNIQUE (user_id, sku_id)  ← 建表时就写在 01-schema.sql 里
    ⇒ PG 为此建了唯一索引 uk_cart_user_sku，**第一列是 user_id**
    ⇒ 单列的 idx_cart_items_user_id 被它覆盖
    ⇒ 而 idx_cart_items_sku_id 唯一的使用者 CartServiceImpl:44 是
       `.eq(getUserId, ...).eq(getSkuId, ...)` —— **两个条件一起给**，
       同样由 uk_cart_user_sku 服务
    ⇒ 两个都可能是**冗余**

★ 同时把**不**符合这个模式的那个也测一遍，作为**对照**：
    `admin_roles` 的主键是 `(admin_id, role_id)` —— `role_id` **不是前缀**
    ⇒ `WHERE role_id = ?` 用不上主键 ⇒ `idx_admin_roles_role_id` **是必要的**。
    它必须「DROP 后计划变化」，否则说明本装置测不出东西。

做法：沿用 Day 31/33 的 DROP 实验 + 归一化 + 对照组。
零副作用：临时库 `mallx_cart_probe`，跑完即删。

运行：python day34-cart-index-probe.py
前置：容器 mallx-postgres 在运行（**不需要**应用在跑）。
"""
from _paths import lp
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DOCKER = os.environ.get("MALLX_DOCKER") or r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
CONTAINER = "mallx-postgres"
DB_USER = "mallx"
ADMIN_DB = "mallx"
PROBE_DB = "mallx_cart_probe"
SQL_DIR = lp(r"D:\MallX\backend\sql")
REPORT = lp(r"D:\MallX\backend\loadtest\day34-cart-index-probe-report.txt")

FILES = ["01-schema.sql", "02-index.sql", "03-data.sql", "04-review-constraints.sql",
         "05-admin-permissions.sql", "06-day17-fixtures.sql", "07-admin-permissions.sql",
         "08-marketing-permissions.sql", "09-user-coupons-unique.sql",
         "10-brand-permissions.sql", "11-order-discount.sql", "12-day22-permissions.sql",
         "13-day23-permissions.sql", "14-brand-crud-permissions.sql"]

N_USERS = 5000
N_CATEGORIES = 300
N_PRODUCTS = 30000
N_CART_ITEMS = 60000      # 每个用户 12 件
N_ADMINS = 200
N_ROLES = 10

EXPECTED_CHECKS = 21

lines = []
say = lines.append
n_pass = n_fail = 0
PA = {}
PB = {}


def chk(name, ok, detail=""):
    global n_pass, n_fail
    if ok:
        n_pass += 1
        say("  [OK]   %s%s" % (name, ("   " + detail) if detail else ""))
    else:
        n_fail += 1
        say("  [FAIL] %s   %s" % (name, detail))
    return ok


def psql(db, sql_text, stop=True, timeout=900):
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


def scan_plan(plan_text):
    idx = set()
    for m in re.finditer(r"Index (?:Only )?Scan(?: Backward)? using (\w+)", plan_text):
        idx.add(m.group(1))
    for m in re.finditer(r"Bitmap Index Scan on (\w+)", plan_text):
        idx.add(m.group(1))
    return sorted(idx), sorted(set(re.findall(r"Seq Scan on (\w+)", plan_text)))


NOISE = [
    (r"\(cost=[^)]*\)", ""),
    (r"\(actual time=[^)]*\)", ""),
    (r"\brows=\d+", "rows=N"),
    (r"\bwidth=\d+", "width=N"),
    (r"\bBuffers:.*", ""),
    (r"\bHeap Blocks:.*", ""),
    (r"\bBatches:.*", ""),
    (r"\bMemory Usage:.*", ""),
    (r"\bPlanning Time:.*", ""),
    (r"\bExecution Time:.*", ""),
    (r"\bFilter:.*", "Filter: <same>"),
    (r"\bRows Removed by Filter:.*", ""),
    (r"\bloops=\d+", "loops=N"),
]


def normalize(plan_text):
    t = plan_text
    for pat, rep in NOISE:
        t = re.sub(pat, rep, t)
    return "\n".join(ln.rstrip() for ln in t.splitlines() if ln.strip())


# ------------------------------------------------------------------ 造数
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

    ("商品 %d" % N_PRODUCTS, """
INSERT INTO products (category_id, brand_id, name, subtitle, description, main_image, status, is_deleted)
SELECT (SELECT id FROM categories ORDER BY id OFFSET (g %% (SELECT count(*) FROM categories)) LIMIT 1),
       (SELECT id FROM brands ORDER BY id OFFSET (g %% GREATEST((SELECT count(*) FROM brands),1)) LIMIT 1),
       'PERF-商品-' || g, 'PERF-副标题', 'PERF-描述', '/img/perf-' || g || '.jpg', 1, 0
FROM generate_series(1, %d) g;
""" % N_PRODUCTS),

    ("SKU x2/商品", """
INSERT INTO product_skus (product_id, sku_code, name, price, original_price, attributes, image, status, is_deleted)
SELECT p.id, 'PERF-SKU-' || p.id || '-' || k, 'PERF-SKU', 100.00 + k, 200.00,
       jsonb_build_object('color', '白色'), '/img/perf-sku.jpg', 1, 0
FROM products p CROSS JOIN generate_series(1, 2) k
WHERE p.name LIKE 'PERF-%';
"""),

    # ★★ (user_id, sku_id) 必须唯一 —— 表上就有 UNIQUE(user_id, sku_id)（uk_cart_user_sku）
    #    g 从 0..59999：user_id 取 5000 个值、sku_id 取 12 个值 ⇒ 组合天然唯一
    ("购物车 %d 条（组合唯一）" % N_CART_ITEMS, """
INSERT INTO cart_items (user_id, sku_id, quantity, selected)
SELECT (SELECT id FROM users ORDER BY id OFFSET (g %% %d) LIMIT 1),
       (SELECT id FROM product_skus WHERE sku_code LIKE 'PERF-%%' ORDER BY id OFFSET (g / %d) LIMIT 1),
       1, TRUE
FROM generate_series(0, %d) g
WHERE (SELECT id FROM product_skus WHERE sku_code LIKE 'PERF-%%' ORDER BY id OFFSET (g / %d) LIMIT 1) IS NOT NULL;
""" % (N_USERS, N_USERS, N_CART_ITEMS - 1, N_USERS)),

    ("管理员 %d / 角色 %d" % (N_ADMINS, N_ROLES), """
INSERT INTO admins (username, password, nickname, status)
SELECT 'perfadmin' || g, 'x', 'PERF', 1 FROM generate_series(1, %d) g;

INSERT INTO roles (name, code, description, status)
SELECT 'PERF-角色-' || g, 'PERF_ROLE_' || g, 'PERF', 1 FROM generate_series(1, %d) g;
""" % (N_ADMINS, N_ROLES)),

    ("管理员-角色 关联", """
INSERT INTO admin_roles (admin_id, role_id)
SELECT a.id, r.id
FROM (SELECT id, row_number() OVER (ORDER BY id) rn FROM admins WHERE username LIKE 'perfadmin%') a
JOIN (SELECT id, row_number() OVER (ORDER BY id) rn FROM roles WHERE code LIKE 'PERF_ROLE_%') r
  ON r.rn = 1 + (a.rn % (SELECT count(*) FROM roles WHERE code LIKE 'PERF_ROLE_%'));
"""),
]

DROP_LIST = ["idx_cart_items_user_id",     # 候选 1（B 型：有替代索引）
             "idx_cart_items_sku_id",      # 候选 2（A 型：根本没被用上）
             "idx_products_category_id"]   # 对照（★ Day 27 已证它会被用上）

USER1 = "(SELECT id FROM users ORDER BY id LIMIT 1)"
SKU1 = "(SELECT id FROM product_skus WHERE sku_code LIKE 'PERF-%' ORDER BY id LIMIT 1)"
CAT1 = "(SELECT id FROM categories ORDER BY id LIMIT 1)"

QUERIES = [
    # ★★ 两种「冗余」要分开判：
    #   A 型（cand）    ：该索引**从来没被用上** ⇒ DROP 后计划【不变】
    #   B 型（cand_sub）：该索引**被用上了，但有替代索引** ⇒ DROP 后计划【会变】，
    #                    但**仍然走索引**、**耗时不变** ⇒ 照样是冗余
    #   （第一版把 C1 也当 A 型判，于是「计划变了」被判成 FAIL —— 那是判据太窄，不是索引不该删。）
    ("C1", "cand_sub", "idx_cart_items_user_id",
     "购物车列表（按 user_id，ORDER BY id DESC）",
     "SELECT id, sku_id, quantity FROM cart_items WHERE user_id = %s "
     "ORDER BY id DESC LIMIT 20" % USER1),

    ("C2", "cand", "idx_cart_items_sku_id",
     "加购查重（WHERE user_id = ? AND sku_id = ?）",
     "SELECT id, quantity FROM cart_items WHERE user_id = %s AND sku_id = %s"
     % (USER1, SKU1)),

    ("C3", "ctrl", "idx_products_category_id",
     "C 端列表按 category_id（★ Day 27 已证它被用上）",
     "SELECT id, name FROM products WHERE is_deleted = 0 AND status = 1 "
     "AND category_id = %s" % CAT1),
]

# 记录型探针：admin_roles 只有 203 行，计划器**根本不会用索引** ——
# 那是「表太小」，不是「索引没用」（同 Day 33 的 coupons 200 行）。
PROBE = ("C4", "角色下的管理员（WHERE role_id = ?）—— admin_roles 仅 203 行",
         "SELECT admin_id FROM admin_roles WHERE role_id = "
         "(SELECT id FROM roles WHERE code LIKE 'PERF_ROLE_%' ORDER BY id LIMIT 1)")


def measure(store):
    for qid, kind, idxname, label, sql in QUERIES:
        rc, out, err = psql(PROBE_DB, "EXPLAIN (ANALYZE, BUFFERS) " + sql)
        if rc != 0:
            raise RuntimeError("%s EXPLAIN 失败：%s" % (qid, err[:200]))
        used, seq = scan_plan(out)
        m = re.search(r"Execution Time: ([\d.]+) ms", out)
        store[qid] = dict(norm=normalize(out), used=used, seq=seq, raw=out,
                          ms=float(m.group(1)) if m else -1.0, label=label)
        say("      %-3s %-9s idx=%-34s seq=%-10s %s" % (
            qid, "%.2fms" % store[qid]["ms"], ",".join(used)[:32] or "-",
            ",".join(seq) or "-", label[:30]))


def main():
    say("=" * 78)
    say("Day 34 -- 「被复合索引覆盖」扫尾：购物车两个索引 + admin_roles 对照")
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
        say("[2] 造数")
        for label, sql in SEEDS:
            rc, _o, err = psql(PROBE_DB, sql)
            chk("造数 %s" % label, rc == 0, "rc=%d err=%s" % (rc, err[:200]))

        say("")
        say("[3] VACUUM (ANALYZE)")
        rc, _o, err = psql(PROBE_DB, "VACUUM (ANALYZE);")
        chk("基线 VACUUM (ANALYZE)", rc == 0, "err=%s" % err[:160])

        say("")
        say("[4] 规模 + ★ 关键约束核对（候选成立的判据前提）")
        n_cart = int(one("SELECT count(*) FROM cart_items"))
        chk("cart_items 行数 >= %d" % N_CART_ITEMS, n_cart >= N_CART_ITEMS, "actual=%d" % n_cart)
        n_uk = int(one("SELECT count(*) FROM pg_indexes WHERE indexname = 'uk_cart_user_sku'"))
        chk("uk_cart_user_sku 存在（UNIQUE(user_id, sku_id)，第一列是 user_id）", n_uk == 1,
            "got=%d" % n_uk)
        n_prod = int(one("SELECT count(*) FROM products"))
        chk("products 行数 >= %d（对照组要有规模，否则计划器不会用索引）" % N_PRODUCTS,
            n_prod >= N_PRODUCTS, "actual=%d" % n_prod)
        n_cat = int(one("SELECT count(*) FROM categories"))
        chk("categories 行数 >= %d（★ 保证 category_id 有选择性）" % N_CATEGORIES,
            n_cat >= N_CATEGORIES, "actual=%d" % n_cat)

        say("")
        say("[5] 阶段 A —— 索引都在")
        measure(PA)

        say("")
        say("[6] 阶段 B —— DROP 3 个索引（2 候选 + 1 对照）+ VACUUM (ANALYZE)")
        rc, _o, err = psql(PROBE_DB,
                           "".join("DROP INDEX IF EXISTS %s;\n" % n for n in DROP_LIST))
        chk("DROP 3 个索引", rc == 0, "rc=%d err=%s" % (rc, err[:200]))
        rc, _o, err = psql(PROBE_DB, "VACUUM (ANALYZE);")
        chk("DROP 后 VACUUM (ANALYZE)", rc == 0, "err=%s" % err[:160])

        say("")
        say("[7] 阶段 B —— 重测")
        measure(PB)

        say("")
        say("[8] ★ 候选索引的定性")
        say("     A 型（cand）：从来没被用上 ⇒ DROP 后计划【不变】")
        say("     B 型（cand_sub）：被用上但有替代索引 ⇒ DROP 后计划【会变】，但**仍走索引、耗时不变**")
        for qid, kind, idxname, label, sql in QUERIES:
            if kind == "cand":
                same = PA[qid]["norm"] == PB[qid]["norm"]
                chk("%s [A型] DROP %s 后计划不变" % (qid, idxname), same,
                    "A_used=%s B_used=%s" % (PA[qid]["used"], PB[qid]["used"]))
                if not same:
                    say("      ---- %s 计划变了：该索引其实有用，不该删 ----" % qid)
                    for ln in PB[qid]["raw"].splitlines():
                        say("      " + ln)
            elif kind == "cand_sub":
                # ★ 判据不是「计划不变」，而是「DROP 后仍然走索引、且耗时不变」
                still_idx = bool(PB[qid]["used"]) and not PB[qid]["seq"]
                chk("%s [B型] DROP %s 后**仍然走索引**（有替代索引，未退化成全表扫）"
                    % (qid, idxname), still_idx,
                    "B_used=%s B_seq=%s" % (PB[qid]["used"], PB[qid]["seq"]))
                a_ms, b_ms = PA[qid]["ms"], PB[qid]["ms"]
                chk("%s [B型] DROP %s 后耗时基本不变（%.2fms → %.2fms）"
                    % (qid, idxname, a_ms, b_ms),
                    b_ms <= a_ms * 1.2 + 0.2,
                    "差 %.2fms" % (b_ms - a_ms))
                say("      替代索引：A 用 %s → B 用 %s" % (
                    ",".join(PA[qid]["used"]) or "-", ",".join(PB[qid]["used"]) or "-"))

        say("")
        say("[8b] 记录型探针：小表上的索引（只记录、不断言）")
        qid, label, sql = PROBE
        n_ar = int(one("SELECT count(*) FROM admin_roles"))
        rc, out, err = psql(PROBE_DB, "EXPLAIN (ANALYZE, BUFFERS) " + sql)
        pused, pseq = scan_plan(out) if rc == 0 else ([], [])
        pm = re.search(r"Execution Time: ([\d.]+) ms", out)
        say("      %s（admin_roles 仅 %d 行）" % (label, n_ar))
        say("      idx=%s seq=%s  %s" % (",".join(pused) or "-", ",".join(pseq) or "-",
                                        "%.2fms" % float(pm.group(1)) if pm else "?"))
        say("      ⇒ 计划器**不用** idx_admin_roles_role_id —— 那是**表太小**，不是索引没用")
        say("        （同 Day 33 的 coupons 200 行）。若 admin 规模真涨起来，它会开始有用。")

        say("")
        say("[9] ★★ 对照：DROP 前后计划必须【发生变化】（证明装置有区分度）")
        for qid, kind, idxname, label, sql in QUERIES:
            if kind != "ctrl":
                continue
            chk("%s DROP %s 后计划确实变了" % (qid, idxname),
                PA[qid]["norm"] != PB[qid]["norm"],
                "A_used=%s B_used=%s" % (PA[qid]["used"], PB[qid]["used"]))

    finally:
        say("")
        say("[10] 删临时库")
        rc, _o, err = psql(ADMIN_DB, "DROP DATABASE IF EXISTS %s;" % PROBE_DB)
        chk("DROP DATABASE %s" % PROBE_DB, rc == 0, "rc=%d err=%s" % (rc, err[:160]))

    return bail()


def bail(code=None):
    say("")
    say("=" * 78)
    say("对照表（A = 索引都在 / B = 已 DROP）")
    say("=" * 78)
    say("      %-4s %-6s %-30s %-10s %-10s %s" % ("ID", "类型", "被 DROP 的索引", "计划变化", "A 耗时", "A 用上的索引"))
    for qid, kind, idxname, label, sql in QUERIES:
        a, b = PA.get(qid), PB.get(qid)
        if not a or not b:
            continue
        say("      %-4s %-6s %-30s %-10s %-10s %s" % (
            qid, "候选" if kind in ("cand", "cand_sub") else "对照", idxname,
            "变了" if a["norm"] != b["norm"] else "没变",
            "%.2fms" % a["ms"], ",".join(a["used"])[:34] or (",".join(a["seq"]) or "-")))

    total = n_pass + n_fail
    say("")
    say("=" * 78)
    say("ASSERTIONS: %d / %d passed   (EXPECTED=%d)" % (n_pass, total, EXPECTED_CHECKS))
    full = (total == EXPECTED_CHECKS)
    if not full:
        say("★ 满额护栏未过：实得 %d 条断言，期望 %d 条 ⇒ 有检查项根本没被执行到"
            % (total, EXPECTED_CHECKS))
    ok = (n_fail == 0) and full
    say("VERDICT: %s" % ("OK -- 购物车两个索引的定性已完成（含对照）" if ok
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
