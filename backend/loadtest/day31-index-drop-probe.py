# -*- coding: utf-8 -*-
"""Day 31 · DROP 实验：把「这个索引没用」从【推断】升级到【实测】。

为什么需要它
------------
Day 30 的索引体检总表里，有 3 个索引被判「值得删」，但**证据等级不一样**：

    idx_products_status          ← day27 实测（计划器从不选它）      → 等级 A
    idx_order_items_sku_id       ← 「无调用方」推断                  → 等级 C
    idx_product_skus_is_deleted  ← 「无调用方」推断                  → 等级 C

★ 判「没有」比判「有」危险得多：判错「有」只是多留一个索引，
  **判错「没有」会删掉一个正在用的东西** —— 而索引删错不会当场报错，
  只会让某条查询在某个数据分布下悄悄慢几十倍。

做法：**DROP 实验**（比 grep 强，比 EXPLAIN 更直接）
---------------------------------------------------
    阶段 A：索引都在 → 跑这几条查询，记下【归一化后的计划】
    阶段 B：把候选索引 DROP 掉 → 再跑同样几条 → 对比计划
    ⇒ 计划**完全不变** = 这个索引对现有查询**零贡献**，删它安全。

★★ 但这套装置必须证明「它有区分度」——所以同时做【对照组】：
  故意 DROP 两个**确实在用**的索引（`idx_orders_user_id` / `idx_products_is_deleted`），
  它们的计划**必须发生变化**。
  没有对照组，「计划没变」可能只是「我这个装置根本测不出变化」。

★ 归一化：把 cost / actual time / rows / width / buffers / loops 全部抹掉，
  只留**计划节点的结构**。不抹掉的话，光是数值抖动就会让「不变」永远判为「变了」。

★ 零副作用：临时库 `mallx_drop_probe`，跑完即删；开发库与生产索引一行不改。

运行：python day31-index-drop-probe.py
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
PROBE_DB = "mallx_drop_probe"
SQL_DIR = lp(r"D:\MallX\backend\sql")
REPORT = lp(r"D:\MallX\backend\loadtest\day31-index-drop-probe-report.txt")

FILES = ["01-schema.sql", "02-index.sql", "03-data.sql", "04-review-constraints.sql",
         "05-admin-permissions.sql", "06-day17-fixtures.sql", "07-admin-permissions.sql",
         "08-marketing-permissions.sql", "09-user-coupons-unique.sql",
         "10-brand-permissions.sql", "11-order-discount.sql", "12-day22-permissions.sql",
         "13-day23-permissions.sql", "14-brand-crud-permissions.sql"]

N_CATEGORIES = 300
N_USERS = 5000
N_PRODUCTS = 30000
N_ORDERS = 30000

EXPECTED_CHECKS = 18

lines = []
say = lines.append
n_pass = n_fail = 0
PA = {}   # 阶段 A（索引都在）
PB = {}   # 阶段 B（候选已 DROP）


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
    (r"\bFilter:.*", "Filter: <same>"),      # 过滤条件随计划器改写而变，不参与结构比较
    (r"\bRows Removed by Filter:.*", ""),
    (r"\bloops=\d+", "loops=N"),
]


def normalize(plan_text):
    """抹掉一切数值噪声，只留计划【节点结构】。★ 不抹的话「不变」永远判为「变了」。"""
    t = plan_text
    for pat, rep in NOISE:
        t = re.sub(pat, rep, t)
    return "\n".join(ln.rstrip() for ln in t.splitlines() if ln.strip())


# ------------------------------------------------------------------ 造数
SEEDS = [
    ("维表 %d 分类" % N_CATEGORIES, """
INSERT INTO categories (parent_id, name, sort_order, status)
SELECT NULL, 'PERF-分类-' || g, 0, 1 FROM generate_series(1, %d) g;
""" % N_CATEGORIES),

    ("维表 %d 用户" % N_USERS, """
INSERT INTO users (username, password, nickname, phone, email, status)
SELECT 'perfuser' || g, 'x', 'PERF', '139' || lpad(g::text, 8, '0'),
       'perf' || g || '@example.com', 1
FROM generate_series(1, %d) g;
""" % N_USERS),

    # status=1 占 99%（低选择性，正是 idx_products_status 被判「没用」的原因）
    ("商品 %d（status=1 占 99%%）" % N_PRODUCTS, """
INSERT INTO products (category_id, brand_id, name, subtitle, description, main_image, status, is_deleted)
SELECT (SELECT id FROM categories ORDER BY id OFFSET (g %% (SELECT count(*) FROM categories)) LIMIT 1),
       (SELECT id FROM brands ORDER BY id OFFSET (g %% GREATEST((SELECT count(*) FROM brands),1)) LIMIT 1),
       'PERF-商品-' || g, 'PERF-副标题', 'PERF-描述', '/img/perf-' || g || '.jpg',
       CASE WHEN g %% 100 = 3 THEN 0 ELSE 1 END, 0
FROM generate_series(1, %d) g;
""" % N_PRODUCTS),

    # is_deleted=0 占 99%（同上，低选择性）
    ("SKU x2/商品（is_deleted=0 占 99%%）", """
INSERT INTO product_skus (product_id, sku_code, name, price, original_price, attributes, image, status, is_deleted)
SELECT p.id, 'PERF-SKU-' || p.id || '-' || k, 'PERF-SKU', 100.00 + k, 200.00,
       jsonb_build_object('color', '白色'), '/img/perf-sku.jpg', 1,
       CASE WHEN p.id % 100 = 3 THEN 1 ELSE 0 END
FROM products p CROSS JOIN generate_series(1, 2) k
WHERE p.name LIKE 'PERF-%';
"""),

    ("订单 %d（user_id 有选择性）" % N_ORDERS, """
INSERT INTO orders (order_no, user_id, total_amount, pay_amount, status,
                    receiver_name, receiver_phone, receiver_address, created_at, updated_at)
SELECT 'PERF-ORD-' || g,
       (SELECT id FROM users ORDER BY id OFFSET (g %% (SELECT count(*) FROM users)) LIMIT 1),
       100.00, 100.00, 'PAID', 'PERF', '13000000000', 'PERF 地址',
       CURRENT_TIMESTAMP - (g || ' minutes')::interval,
       CURRENT_TIMESTAMP - (g || ' minutes')::interval
FROM generate_series(1, %d) g;
""" % N_ORDERS),
]

# ------------------------------------------------------------------ 查询集
# kind: "cand" = 候选索引（DROP 后计划应【不变】）
#       "ctrl" = 对照索引（DROP 后计划应【变化】）—— 证明装置有区分度
SUB_CAT = "(SELECT id FROM categories ORDER BY id LIMIT 1)"
SUB_USER = "(SELECT id FROM users ORDER BY id LIMIT 1)"

QUERIES = [
    ("P1", "cand", "idx_products_status",
     "C 端商品列表（status = 1 + ORDER BY id DESC LIMIT 10）",
     "SELECT id, name FROM products WHERE is_deleted = 0 AND status = 1 ORDER BY id DESC LIMIT 10"),

    ("P2", "cand", "idx_product_skus_is_deleted",
     "商品列表带 SKU 存在性（is_deleted = 0 AND status = 1）",
     "SELECT p.id FROM products p WHERE p.is_deleted = 0 AND p.status = 1 "
     "AND EXISTS (SELECT 1 FROM product_skus s WHERE s.product_id = p.id "
     "            AND s.is_deleted = 0 AND s.status = 1) LIMIT 10"),

    ("C1", "ctrl", "idx_orders_user_id",
     "我的订单列表（按 user_id）",
     "SELECT id FROM orders WHERE user_id = %s ORDER BY id DESC LIMIT 10" % SUB_USER),

    ("C2", "ctrl", "idx_products_is_deleted",
     "管理端商品计数（is_deleted = 0）",
     "SELECT count(*) FROM products WHERE is_deleted = 0"),
]


def measure(store):
    for qid, kind, idxname, label, sql in QUERIES:
        rc, out, err = psql(PROBE_DB, "EXPLAIN (ANALYZE, BUFFERS) " + sql)
        if rc != 0:
            raise RuntimeError("%s EXPLAIN 失败：%s" % (qid, err[:200]))
        used, seq = scan_plan(out)
        store[qid] = dict(norm=normalize(out), used=used, seq=seq,
                          raw=out, label=label, idx=idxname, kind=kind)
        say("      %-3s idx=%-32s seq=%-14s %s" % (
            qid, ",".join(used)[:30] or "-", ",".join(seq) or "-", label[:24]))


def main():
    say("=" * 78)
    say("Day 31 -- DROP 实验：候选索引删掉之后，计划会不会变？（临时库 %s）" % PROBE_DB)
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
        say("[3] VACUUM (ANALYZE)（★ Day 27 教训：只 ANALYZE 会得到会翻转的结论）")
        rc, _o, err = psql(PROBE_DB, "VACUUM (ANALYZE);")
        chk("基线 VACUUM (ANALYZE)", rc == 0, "err=%s" % err[:160])

        say("")
        say("[4] 规模核对（★ 没有规模，索引本来就无胜算，实验等于没做）")
        for tbl, want in [("products", N_PRODUCTS), ("product_skus", N_PRODUCTS * 2),
                          ("orders", N_ORDERS)]:
            got = int(one("SELECT count(*) FROM %s" % tbl))
            chk("%s 行数 >= %d" % (tbl, want), got >= want, "actual=%d" % got)

        say("")
        say("[5] 阶段 A —— 索引都在（4 个索引：2 候选 + 2 对照）")
        measure(PA)

        say("")
        say("[6] 阶段 B —— 把这 4 个索引 DROP 掉 + VACUUM (ANALYZE)")
        names = [q[2] for q in QUERIES]
        rc, _o, err = psql(PROBE_DB,
                           "".join("DROP INDEX IF EXISTS %s;\n" % n for n in names))
        chk("DROP 4 个索引", rc == 0, "rc=%d err=%s" % (rc, err[:200]))
        rc, _o, err = psql(PROBE_DB, "VACUUM (ANALYZE);")
        chk("DROP 后 VACUUM (ANALYZE)", rc == 0, "err=%s" % err[:160])

        say("")
        say("[7] 阶段 B —— 重测")
        measure(PB)

        say("")
        say("[8] ★ 候选索引：DROP 前后计划必须【完全不变】（不变 ⇒ 删它安全）")
        for qid, kind, idxname, label, sql in QUERIES:
            if kind != "cand":
                continue
            same = PA[qid]["norm"] == PB[qid]["norm"]
            chk("%s DROP %s 后计划不变" % (qid, idxname), same,
                "A_used=%s B_used=%s" % (PA[qid]["used"], PB[qid]["used"]))
            if not same:
                say("      ---- 计划变了（说明该索引其实有用，不该删）----")
                for ln in PB[qid]["raw"].splitlines():
                    say("      " + ln)

        say("")
        say("[9] ★★ 对照组：DROP 前后计划必须【发生变化】—— 证明本装置有区分度")
        say("     （没有这一步，「计划不变」可能只是「装置根本测不出变化」）")
        for qid, kind, idxname, label, sql in QUERIES:
            if kind != "ctrl":
                continue
            diff = PA[qid]["norm"] != PB[qid]["norm"]
            chk("%s DROP %s 后计划确实变了" % (qid, idxname), diff,
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
    say("      %-4s %-6s %-32s %-12s %s" % ("ID", "类型", "被 DROP 的索引", "计划变化", "A 用上的索引"))
    for qid, kind, idxname, label, sql in QUERIES:
        a, b = PA.get(qid), PB.get(qid)
        if not a or not b:
            continue
        changed = "变了" if a["norm"] != b["norm"] else "没变"
        say("      %-4s %-6s %-32s %-12s %s" % (
            qid, "候选" if kind == "cand" else "对照", idxname, changed,
            ",".join(a["used"])[:34] or (",".join(a["seq"]) or "-")))

    total = n_pass + n_fail
    say("")
    say("=" * 78)
    say("ASSERTIONS: %d / %d passed   (EXPECTED=%d)" % (n_pass, total, EXPECTED_CHECKS))
    full = (total == EXPECTED_CHECKS)
    if not full:
        say("★ 满额护栏未过：实得 %d 条断言，期望 %d 条 ⇒ 有检查项根本没被执行到"
            % (total, EXPECTED_CHECKS))
    ok = (n_fail == 0) and full
    say("VERDICT: %s" % ("OK -- 候选索引对现有查询零贡献（且对照组证明装置有区分度）" if ok
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
