# -*- coding: utf-8 -*-
"""Day 28 预研 · 「让全文检索真正走上索引」的三个候选改法，谁真的更快？

背景（Day 27 实测）
------------------
`searchProducts` 的 WHERE 是

    (search_vector @@ plainto_tsquery(...)
     OR name ILIKE '%kw%' OR subtitle ILIKE '%kw%' OR description ILIKE '%kw%')

后两支 ILIKE 的列**没有索引** ⇒ 拼不出 `BitmapOr` ⇒ 只能全表扫。
同一条 SQL 去掉 OR 之后 GIN 立刻被用上：**1.3ms vs 68.5ms**。

三个候选（都只改 SQL / 索引，不改业务语义）
------------------------------------------
  V0  现状：OR 四支（基线，用来对照）
  V1  给 `subtitle` / `description` 补 `pg_trgm` GIN ⇒ 让 `BitmapOr` 四支都有索引可走
  V2  把 OR 拆成 `UNION`（四支各走各的索引，再由 UNION 去重）
  V3  只留全文（去掉 ILIKE 兜底）—— ★ 只作参照，**不是可选项**，见下

★★ V3 为什么不是可选项：中文。
   `to_tsvector('simple', ...)` 不切中文，整段中文会变成**一个 token**
   ⇒ `keyword=笔记本` 走全文**恒返回 0 条**（Day 20 的 L3「搜索黑洞」就是这个）。
   所以 ILIKE 兜底对中文是**功能**，不是优化。V3 存在的意义是**把这件事量化**。

★★ 本脚本最重要的判据不是「谁快」，而是 **「谁快且结果集不变」**：
  快 10 倍但少返回 20 行的改法不是优化，是缺陷。所以每个变体都要和 V0 对**行数**。

★ 顺序很关键：V0/V3 必须在**补索引之前**测，V1/V2 在**之后**测 ——
  否则 V0 会白蹭 V1 的索引，对照就废了。

做法：临时库 `mallx_search_probe`（与 day25/day27 同一套路），
      灌 01→14 + 造数 → `VACUUM (ANALYZE)` → 逐变体 `EXPLAIN (ANALYZE, BUFFERS)`
      → DROP DATABASE。**开发库零改动、生产 SQL 一行不改。**

运行：python day28-search-rewrite-probe.py
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
PROBE_DB = "mallx_search_probe"
SQL_DIR = lp(r"D:\MallX\backend\sql")
REPORT = lp(r"D:\MallX\backend\loadtest\day28-search-rewrite-probe-report.txt")

FILES = ["01-schema.sql", "02-index.sql", "03-data.sql", "04-review-constraints.sql",
         "05-admin-permissions.sql", "06-day17-fixtures.sql", "07-admin-permissions.sql",
         "08-marketing-permissions.sql", "09-user-coupons-unique.sql",
         "10-brand-permissions.sql", "11-order-discount.sql", "12-day22-permissions.sql",
         "13-day23-permissions.sql", "14-brand-crud-permissions.sql"]

N_CATEGORIES = 300
N_PRODUCTS = 30000
RARE = 1000          # 每 1000 个里 1 个 ⇒ 0.1%（★ Day 27 教训：必须造出选择性）
CN = "笔记本"
# ★★ 中文词必须写成【连续无空格的 CJK 串】。
#    第一版写成 ' 笔记本'（前面带空格）⇒ 它成了一个**独立的 token** ⇒ 全文居然能命中
#    （V3 对中文返回 90 行，与「中文走全文恒为 0」的预期相反）。
#    而真实中文没有空格：整段是一个 token，查 '笔记本' 必然匹配不上 —— 这才是
#    「搜索黑洞」的真实成因，也是 ILIKE 兜底存在的理由。
#    ⇒ 判据：**样本必须落在判据的取值域里**（本脚本第 4 次踩这条）。
CN_NAME_SUFFIX = "笔记本高清屏"
CN_DESC_SUFFIX = "笔记本超薄机身"

EXPECTED_CHECKS = 24

lines = []
say = lines.append
n_pass = n_fail = 0
RESULTS = {}          # (variant, label) -> dict(rows=, idx=, seq=, ms=)


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


# ------------------------------------------------------------------ 造数
SEEDS = [
    ("维表 %d 分类" % N_CATEGORIES, """
INSERT INTO categories (parent_id, name, sort_order, status)
SELECT NULL, 'PERF-分类-' || g, 0, 1 FROM generate_series(1, %d) g;
""" % N_CATEGORIES),

    # ★ 中文词的三种落点，专门用来验 UNION 有没有去重
    #   g%%1000==1 → 只在 name ；==2 → 只在 description ；==3 → 两边都有
    ("商品 %d 行（iphone 0.1%% / %s 三种落点）" % (N_PRODUCTS, CN), """
INSERT INTO products (category_id, brand_id, name, subtitle, description, main_image, status, is_deleted)
SELECT (SELECT id FROM categories ORDER BY id OFFSET (g %% (SELECT count(*) FROM categories)) LIMIT 1),
       (SELECT id FROM brands ORDER BY id OFFSET (g %% GREATEST((SELECT count(*) FROM brands),1)) LIMIT 1),
       'PERF-商品-' || g || ' 手机'
         || CASE WHEN g %% %d = 0 THEN ' iphone' ELSE '' END
         || CASE WHEN g %% %d IN (1, 3) THEN ' %s' ELSE '' END,
       'PERF-副标题-' || g || ' 轻薄便携',
       'PERF-描述-' || g || ' 高性能办公'
         || CASE WHEN g %% %d IN (2, 3) THEN ' %s' ELSE '' END,
       '/img/perf-' || g || '.jpg',
       1, 0
FROM generate_series(1, %d) g;
""" % (RARE, RARE, CN_NAME_SUFFIX, RARE, CN_DESC_SUFFIX, N_PRODUCTS)),

    ("SKU x2/商品", """
INSERT INTO product_skus (product_id, sku_code, name, price, original_price, attributes, image, status, is_deleted)
SELECT p.id, 'PERF-SKU-' || p.id || '-' || k, 'PERF-SKU', 100.00 + k, 200.00,
       jsonb_build_object('color', '白色'), '/img/perf-sku.jpg', 1, 0
FROM products p CROSS JOIN generate_series(1, 2) k
WHERE p.name LIKE 'PERF-%';
"""),
]

EXTRA_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_products_subtitle_trgm ON products USING GIN (subtitle gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_products_description_trgm ON products USING GIN (description gin_trgm_ops);
"""

BASE = "p.is_deleted = 0 AND p.status = 1"
FTS = "p.search_vector @@ plainto_tsquery('simple', '{kw}')"
I_NAME = "p.name ILIKE '%{kw}%'"
I_SUB = "p.subtitle ILIKE '%{kw}%'"
I_DESC = "p.description ILIKE '%{kw}%'"

OR_SQL = "SELECT p.id FROM products p WHERE %s AND (%s OR %s OR %s OR %s)" % (BASE, FTS, I_NAME, I_SUB, I_DESC)
UNION_BODY = ("SELECT p.id FROM products p WHERE %s AND (%s) "
              "UNION SELECT p.id FROM products p WHERE %s AND (%s) "
              "UNION SELECT p.id FROM products p WHERE %s AND (%s) "
              "UNION SELECT p.id FROM products p WHERE %s AND (%s)"
              % (BASE, FTS, BASE, I_NAME, BASE, I_SUB, BASE, I_DESC))
FTS_ONLY = "SELECT p.id FROM products p WHERE %s AND (%s)" % (BASE, FTS)

SQL = {
    "V0": OR_SQL,
    "V1": OR_SQL,                                        # 同 SQL，差别只在库里有没有额外索引
    "V2": UNION_BODY,
    "V3": FTS_ONLY,
}
TIMED = {
    "V0": OR_SQL + " LIMIT 10",
    "V1": OR_SQL + " LIMIT 10",
    "V2": "SELECT * FROM (%s) u LIMIT 10" % UNION_BODY,
    "V3": FTS_ONLY + " LIMIT 10",
}

KEYWORDS = [("EN", "iphone"), ("CN", CN)]
PHASE_A = ["V0", "V3"]      # 补索引【之前】测
PHASE_B = ["V1", "V2"]      # 补索引【之后】测


def run_variant(v, label, kw):
    sql = SQL[v].replace("{kw}", kw)
    rows = int(one("SELECT count(*) FROM (%s) t" % sql))
    rc, out, err = psql(PROBE_DB, "EXPLAIN (ANALYZE, BUFFERS) " + TIMED[v].replace("{kw}", kw))
    idx, seq = scan_plan(out) if rc == 0 else ([], [])
    m = re.search(r"Execution Time: ([\d.]+) ms", out)
    ms = float(m.group(1)) if m else -1.0
    RESULTS[(v, label)] = dict(rows=rows, idx=idx, seq=seq, ms=ms)
    say("      %-3s rows=%-6d %-9s idx=%s seq=%s" % (
        v, rows, "%.2fms" % ms, idx or "-", seq or "-"))
    return rows


def main():
    say("=" * 78)
    say("Day 28 预研 -- 让全文检索走上索引：三个候选改法，谁快且结果不变？")
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
        say("[4] 选择性核对（★ 没有选择性，任何改法都看不出差别）")
        for label, kw in KEYWORDS:
            n = int(one("SELECT count(*) FROM products "
                        "WHERE name ILIKE '%%%s%%' OR description ILIKE '%%%s%%'" % (kw, kw)))
            chk("%s 关键词 '%s' 命中 < 5%%" % (label, kw),
                0 < n < N_PRODUCTS * 0.05, "hit=%d / %d" % (n, N_PRODUCTS))

        # ---------- 5. 阶段 A：补索引【之前】 ----------
        say("")
        say("[5] 阶段 A —— 补索引【之前】测 V0（现状）/ V3（只留全文，参照项）")
        for label, kw in KEYWORDS:
            say("")
            say("  --- %s 关键词 '%s' ---" % (label, kw))
            for v in PHASE_A:
                run_variant(v, label, kw)

        # ---------- 6. 补索引 ----------
        say("")
        say("[6] 补 trgm 索引（★ 只在临时库里建）+ VACUUM (ANALYZE)")
        rc, _o, err = psql(PROBE_DB, EXTRA_INDEXES)
        chk("CREATE INDEX idx_products_subtitle_trgm / description_trgm",
            rc == 0, "rc=%d err=%s" % (rc, err[:200]))
        rc, _o, err = psql(PROBE_DB, "VACUUM (ANALYZE);")
        chk("补索引后 VACUUM (ANALYZE)", rc == 0, "err=%s" % err[:160])

        # ---------- 7. 阶段 B：补索引【之后】 ----------
        say("")
        say("[7] 阶段 B —— 补索引【之后】测 V1（同 SQL）/ V2（OR 拆 UNION）")
        for label, kw in KEYWORDS:
            say("")
            say("  --- %s 关键词 '%s' ---" % (label, kw))
            base = RESULTS[("V0", label)]["rows"]
            for v in PHASE_B:
                rows = run_variant(v, label, kw)
                # ★ 正确性：结果行数必须与 V0 完全相等，否则不是优化是缺陷
                chk("%s/%s 结果行数与 V0 相等（%d）" % (v, label, base),
                    rows == base, "V0=%d 本变体=%d" % (base, rows))

        # ---------- 8. V3 的意义 ----------
        say("")
        say("[8] ★ V3（去掉 ILIKE 兜底）为什么不可选 —— 中文")
        chk("V3 对中文 '%s' 返回 0 行（全文不切中文）" % CN,
            RESULTS[("V3", "CN")]["rows"] == 0, "rows=%d" % RESULTS[("V3", "CN")]["rows"])
        chk("V0 对中文 '%s' 返回 > 0 行（兜底在起作用）" % CN,
            RESULTS[("V0", "CN")]["rows"] > 0, "rows=%d" % RESULTS[("V0", "CN")]["rows"])
        say("      ⇒ ILIKE 兜底对中文是【功能】，任何改法都必须保住它。")

        # ---------- 9. UNION 必须去重 ----------
        say("")
        say("[9] ★ V2 必须用 UNION 而不是 UNION ALL")
        naive = int(one("SELECT count(*) FROM (%s) t" % UNION_BODY.replace("{kw}", CN)
                        .replace("UNION SELECT", "UNION ALL SELECT")))
        un = RESULTS[("V2", "CN")]["rows"]
        v0 = RESULTS[("V0", "CN")]["rows"]
        chk("V2(UNION) 行数 == V0 行数（语义等价）", un == v0, "V2=%d V0=%d" % (un, v0))
        chk("UNION ALL 会多出行（证明必须去重）", naive > un,
            "UNION ALL=%d UNION=%d" % (naive, un))

        # ---------- 10. 关键计划断言 ----------
        say("")
        say("[10] 关键计划断言")
        r = RESULTS
        chk("V0/CN 走 Seq Scan（现状确认）", "products" in r[("V0", "CN")]["seq"],
            "seq=%s" % r[("V0", "CN")]["seq"])
        chk("V1/CN 用上 trgm 索引（补索引后 OR 能拼出 BitmapOr）",
            any("trgm" in i for i in r[("V1", "CN")]["idx"]), "idx=%s" % r[("V1", "CN")]["idx"])
        chk("V2/CN 用上 trgm 索引（UNION 各支独立走索引）",
            any("trgm" in i for i in r[("V2", "CN")]["idx"]), "idx=%s" % r[("V2", "CN")]["idx"])
        chk("V0/EN 不用 idx_products_search（OR 挡住 GIN）",
            "idx_products_search" not in r[("V0", "EN")]["idx"], "idx=%s" % r[("V0", "EN")]["idx"])
        chk("V1/EN 用上索引（GIN 或 trgm）",
            any("trgm" in i for i in r[("V1", "EN")]["idx"])
            or "idx_products_search" in r[("V1", "EN")]["idx"],
            "idx=%s" % r[("V1", "EN")]["idx"])

    finally:
        say("")
        say("[11] 删临时库")
        rc, _o, err = psql(ADMIN_DB, "DROP DATABASE IF EXISTS %s;" % PROBE_DB)
        chk("DROP DATABASE %s" % PROBE_DB, rc == 0, "rc=%d err=%s" % (rc, err[:160]))

    return bail()


def bail(code=None):
    say("")
    say("=" * 78)
    say("变体对比（rows = 结果行数；ms = 带 LIMIT 10 的执行时间）")
    say("=" * 78)
    say("      %-10s %-7s %-10s %-24s %s" % ("变体", "rows", "耗时", "用上的索引", "Seq Scan"))
    for label, kw in KEYWORDS:
        say("      --- %s ('%s') ---" % (label, kw))
        for v in ["V0", "V1", "V2", "V3"]:
            rr = RESULTS.get((v, label))
            if not rr:
                continue
            say("      %-10s %-7d %-10s %-24s %s" % (
                v, rr["rows"], "%.2fms" % rr["ms"],
                (",".join(rr["idx"])[:22] if rr["idx"] else "-"),
                (",".join(rr["seq"]) if rr["seq"] else "-")))
        say("")

    total = n_pass + n_fail
    say("=" * 78)
    say("ASSERTIONS: %d / %d passed   (EXPECTED=%d)" % (n_pass, total, EXPECTED_CHECKS))
    full = (total == EXPECTED_CHECKS)
    if not full:
        say("★ 满额护栏未过：实得 %d 条断言，期望 %d 条 ⇒ 有检查项根本没被执行到"
            % (total, EXPECTED_CHECKS))
    ok = (n_fail == 0) and full
    say("VERDICT: %s" % ("OK -- 三个候选改法已量化，结果集等价性成立" if ok
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
