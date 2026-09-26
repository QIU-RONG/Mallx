# -*- coding: utf-8 -*-
"""Day 28 · 搜索修复的落地验收：结果集等价 + 计划真的走上新索引。

为什么需要它
------------
Day 28 的预研（`day28-search-rewrite-probe.py`，24/24）证明 V1「只补 trgm 索引、
SQL 不动」最快（EN 23.74→0.82 ms）且**结果集与 V0 逐行相等**。
但预研是临时对照，落地后必须有一份**常驻验收**回答两件事：

  1. **没有变快但变错** —— 15 号补丁前后，真实搜索 SQL 的 id 序列必须逐一相等
     （全量比对 + 生产形状 top-10 比对 ⇒ 连分页内容都不会变）。
  2. **索引真的被用上了** —— 「建好了」与「计划器开始用它」之间隔着统计信息
     （Day 27 的教训）⇒ 用 EXPLAIN 断言，不靠感觉。

★★ 两条查询形状各有分工（第一版踩过的坑，别再合并）：
  · **生产原形（含 LIMIT 10）** —— 计划断言用。LIMIT 让 top-N 排序便宜，
    计划器才会选 BitmapOr（day27 Q5 = 1.4ms 的那个形状）。
  · **全量（去 LIMIT）** —— 等价性比对用。第一版把它俩合并成「去 LIMIT」一条，
    结果计划器**合法地**退回 Seq Scan（无 LIMIT 时随机堆取回的估算代价压过索引
    收益）⇒ 五条计划断言全挂。**样本必须落在判据的取值域里**（本proj第 5 次）。

做法（★ 零副作用，一次运行内自带 A/B）
------------------
临时库 `mallx_search_verify` → 灌 01→15 → 造数（关键词只落在 subtitle /
description 的商品必须存在，否则新索引没有可证明的价值）：

    阶段 V0：DROP 两列新 trgm ⇒ 复现修复前（OR 拼不出 BitmapOr ⇒ Seq Scan）
    阶段 V1：重建 + VACUUM (ANALYZE) ⇒ 断言 id 序列与 V0 逐一相等 + 计划含新 trgm
    （耗时只记录不断言 —— 计时断言在共享硬件上会抖，等价性/计划才是护栏）

★★ 三处统计信息必须用 VACUUM (ANALYZE)，**裸 ANALYZE 不行**（CI 红本地绿的实锤）：
  批量 INSERT 后 30k 行全在 GIN pending list 里，ANALYZE **不清 pending**，
  planner 给含 GIN 的 BitmapOr 估出天价 ⇒ 整个 OR 翻成 Seq Scan（idx=-，5 条计划断言
  全挂，而等价性/pg_indexes 全过）。本地跑得慢、autovacuum 时机不同 ⇒ 偶发分叉。
  与 rewrite-probe「Day 27 教训」同一招。

运行：python day28-search-index-verify.py
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
PROBE_DB = "mallx_search_verify"
SQL_DIR = lp(r"D:\MallX\backend\sql")
REPORT = lp(r"D:\MallX\backend\loadtest\day28-search-index-verify-report.txt")

NEW_TRGM = ["idx_products_subtitle_trgm", "idx_products_description_trgm"]

FILES = ["01-schema.sql", "02-index.sql", "03-data.sql", "04-review-constraints.sql",
         "05-admin-permissions.sql", "06-day17-fixtures.sql", "07-admin-permissions.sql",
         "08-marketing-permissions.sql", "09-user-coupons-unique.sql",
         "10-brand-permissions.sql", "11-order-discount.sql", "12-day22-permissions.sql",
         "13-day23-permissions.sql", "14-brand-crud-permissions.sql",
         "15-search-trgm-indexes.sql"]

N_PRODUCTS = 30000
EXPECTED_CHECKS = 15

lines = []
say = lines.append
n_pass = n_fail = 0


def chk(name, ok, detail=""):
    global n_pass, n_fail
    if ok:
        n_pass += 1
        say("  [OK]   %s%s" % (name, ("   " + detail) if detail else ""))
    else:
        n_fail += 1
        say("  [FAIL] %s   %s" % (name, detail))
    return ok


def psql(db, sql_text, timeout=900):
    args = [DOCKER, "exec", "-i", "-e", "PGCLIENTENCODING=UTF8",
            CONTAINER, "psql", "-U", DB_USER, "-d", db,
            "-v", "ON_ERROR_STOP=1", "-t", "-A", "-F", "|"]
    p = subprocess.run(args, input=sql_text, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return (p.returncode,
            (p.stdout or "").replace("\r", "").strip(),
            (p.stderr or "").replace("\r", "").strip())


def one(sql):
    rc, out, err = psql(PROBE_DB, sql)
    if rc != 0:
        raise RuntimeError("SQL 失败 rc=%d err=%s\n%s" % (rc, err[:300], sql[:200]))
    return out


# ---- 两条 SQL × 两种形状 ------------------------------------------------
# 生产原形（含 LIMIT 10）：计划断言用 —— 与 day27 Q5/Q6 同形
Q5P = ("SELECT p.id FROM products p WHERE p.is_deleted = 0 AND p.status = 1 "
       "AND (p.search_vector @@ plainto_tsquery('simple','iphone') "
       "     OR p.name ILIKE '%iphone%' OR p.subtitle ILIKE '%iphone%' OR p.description ILIKE '%iphone%') "
       "ORDER BY ts_rank(p.search_vector, plainto_tsquery('simple','iphone')) DESC, p.id ASC LIMIT 10")
Q6P = ("SELECT p.id FROM products p WHERE p.is_deleted = 0 AND p.status = 1 "
       "AND (p.name ILIKE '%笔记本%' OR p.subtitle ILIKE '%笔记本%' OR p.description ILIKE '%笔记本%') LIMIT 10")
# 全量（去 LIMIT）：等价性比对用
Q5F = Q5P.replace(" LIMIT 10", "")
Q6F = Q6P.replace(" LIMIT 10", "")


def ids_of(sql):
    return one(sql).splitlines()


def explain_idx(sql):
    """EXPLAIN 后提取用到的索引名集合（与 day27 同款正则）；★ 失败必须炸，不许吞。"""
    rc, plan, err = psql(PROBE_DB, "EXPLAIN (ANALYZE) %s" % sql)
    if rc != 0:
        raise RuntimeError("EXPLAIN 失败 rc=%d err=%s" % (rc, err[:300]))
    idx = set()
    for m in re.finditer(r"Index (?:Only )?Scan(?: Backward)? using (\w+)", plan):
        idx.add(m.group(1))
    for m in re.finditer(r"Bitmap Index Scan on (\w+)", plan):
        idx.add(m.group(1))
    return idx, plan


SEED = """
INSERT INTO products (category_id, brand_id, name, subtitle, description, main_image, status, is_deleted)
SELECT (SELECT min(id) FROM categories), (SELECT min(id) FROM brands),
       CASE WHEN g %% 1000 = 0 THEN 'PERF-phone-' || g || ' iphone'
            WHEN g %% 1000 = 1 THEN 'PERF-cn-' || g || ' 笔记本'
            ELSE 'PERF-商品-' || g END,
       CASE WHEN g %% 1000 = 2 THEN ' portable iphone'
            WHEN g %% 1000 = 3 THEN ' 轻薄 笔记本'
            ELSE '副标题' END,
       CASE WHEN g %% 1000 = 4 THEN 'apple iphone like new'
            WHEN g %% 1000 = 3 THEN '办公 笔记本 高清屏'
            ELSE '描述' END,
       '/img/p-' || g || '.jpg', 1, 0
FROM generate_series(1, %d) g;
VACUUM (ANALYZE) products;
""" % N_PRODUCTS


def main():
    say("=" * 78)
    say("Day 28 · 搜索修复落地验收（V0 修复前 vs V1 修复后，同库 A/B）")
    say("=" * 78)

    say("")
    say("[0] 建临时库（★ 只动这一个名字，开发库不碰）")
    rc, _o, err = psql(ADMIN_DB, "DROP DATABASE IF EXISTS %s;\nCREATE DATABASE %s;" % (PROBE_DB, PROBE_DB))
    chk("CREATE DATABASE %s" % PROBE_DB, rc == 0, "rc=%d err=%s" % (rc, err[:160]))
    if rc != 0:
        return bail()

    try:
        say("")
        say("[1] 按序灌 01→15（含 15 号补丁：subtitle/description trgm）")
        bad = []
        for name in FILES:
            rc, _o, err = psql(PROBE_DB, open(os.path.join(SQL_DIR, name), encoding="utf-8").read())
            if rc != 0:
                bad.append(name)
                say("      [FAIL] %s   %s" % (name, err.replace("\n", " | ")[:200]))
        chk("15 份补丁全部 rc == 0", not bad, "bad=%s" % bad)
        if bad:
            return bail()

        say("")
        say("[2] 造数 %d 商品（关键词落点：name/subtitle/description 各有专属命中组）" % N_PRODUCTS)
        one(SEED)
        perf_rows = int(one("SELECT count(*) FROM products WHERE name LIKE 'PERF-%'"))
        chk("PERF 商品行数 == %d" % N_PRODUCTS, perf_rows == N_PRODUCTS, "actual=%d" % perf_rows)

        say("")
        say("[3] ★ 阶段 V0 —— DROP 两列新 trgm，复现修复前")
        one("DROP INDEX %s;\nDROP INDEX %s;\nVACUUM (ANALYZE) products;" % (NEW_TRGM[0], NEW_TRGM[1]))
        idx5p_v0, _p = explain_idx(Q5P)
        t0 = time.time(); ids5f_v0 = ids_of(Q5F); ms5f_v0 = (time.time() - t0) * 1000
        t0 = time.time(); ids6f_v0 = ids_of(Q6F); ms6f_v0 = (time.time() - t0) * 1000
        ids5p_v0 = ids_of(Q5P)
        say("      V0-Q5F: %d 行, %.1f ms（全量比对用）" % (len(ids5f_v0), ms5f_v0))
        say("      V0-Q6F: %d 行, %.1f ms（全量比对用）" % (len(ids6f_v0), ms6f_v0))
        say("      V0-Q5P: 索引=%s（生产形状，计划断言用）" % (",".join(sorted(idx5p_v0)) or "-"))
        chk("V0-Q5P 无任何 trgm 索引可走（OR 拼不出 BitmapOr ⇒ 修复前的病灶）",
            not any("trgm" in i for i in idx5p_v0), "idx=%s" % (",".join(sorted(idx5p_v0)) or "-"))
        chk("V0-Q6F 行数 > 0（中文兜底必须真的能查到东西）", len(ids6f_v0) > 0, "rows=%d" % len(ids6f_v0))

        say("")
        say("[4] ★ 阶段 V1 —— 重建两列 trgm + ANALYZE")
        one("CREATE INDEX IF NOT EXISTS %s ON products USING GIN (subtitle gin_trgm_ops);\n"
            "CREATE INDEX IF NOT EXISTS %s ON products USING GIN (description gin_trgm_ops);\n"
            "VACUUM (ANALYZE) products;" % (NEW_TRGM[0], NEW_TRGM[1]))

        idx5p_v1, p5 = explain_idx(Q5P)
        idx6p_v1, p6 = explain_idx(Q6P)
        t0 = time.time(); ids5f_v1 = ids_of(Q5F); ms5f_v1 = (time.time() - t0) * 1000
        t0 = time.time(); ids6f_v1 = ids_of(Q6F); ms6f_v1 = (time.time() - t0) * 1000
        ids5p_v1 = ids_of(Q5P)
        say("      V1-Q5F: %d 行, %.1f ms" % (len(ids5f_v1), ms5f_v1))
        say("      V1-Q6F: %d 行, %.1f ms" % (len(ids6f_v1), ms6f_v1))
        say("      V1-Q5P: 索引=%s" % (",".join(sorted(idx5p_v1)) or "-"))
        say("      V1-Q6P: 索引=%s" % (",".join(sorted(idx6p_v1)) or "-"))

        say("")
        say("[5] ★★ 等价性：V1 的 id 序列与 V0 逐一相等（含排序 ⇒ 分页内容不变）")
        chk("Q5 全量 id 序列逐一相等（%d 行）" % len(ids5f_v0), ids5f_v1 == ids5f_v0,
            "v0=%d v1=%d" % (len(ids5f_v0), len(ids5f_v1)))
        chk("Q6 全量 id 序列逐一相等（%d 行）" % len(ids6f_v0), ids6f_v1 == ids6f_v0,
            "v0=%d v1=%d" % (len(ids6f_v0), len(ids6f_v1)))
        chk("Q5 生产形状 top-10 序列逐一相等", ids5p_v1 == ids5p_v0,
            "v0=%s v1=%s" % (",".join(ids5p_v0[:3]) + "...", ",".join(ids5p_v1[:3]) + "..."))

        say("")
        say("[6] ★★ 计划真的走上新索引（生产形状；「建好了」≠「被用上」，Day 27 的教训）")
        chk("V1-Q5P 计划含 idx_products_subtitle_trgm", "idx_products_subtitle_trgm" in idx5p_v1,
            "idx=%s" % (",".join(sorted(idx5p_v1)) or "-"))
        chk("V1-Q5P 计划含 idx_products_description_trgm", "idx_products_description_trgm" in idx5p_v1,
            "idx=%s" % (",".join(sorted(idx5p_v1)) or "-"))
        chk("V1-Q6P 计划含 idx_products_name_trgm", "idx_products_name_trgm" in idx6p_v1,
            "idx=%s" % (",".join(sorted(idx6p_v1)) or "-"))
        chk("V1-Q6P 计划含 idx_products_subtitle_trgm", "idx_products_subtitle_trgm" in idx6p_v1,
            "idx=%s" % (",".join(sorted(idx6p_v1)) or "-"))
        chk("V1-Q6P 计划含 idx_products_description_trgm", "idx_products_description_trgm" in idx6p_v1,
            "idx=%s" % (",".join(sorted(idx6p_v1)) or "-"))

        say("")
        say("[7] 三列 trgm 在 pg_indexes 里齐（对照 day19 的口径）")
        have = one("SELECT indexname FROM pg_indexes WHERE tablename='products' AND indexname LIKE 'idx_products_%_trgm' ORDER BY 1")
        chk("pg_indexes 里 trgm 索引 == 3 个", len(have.splitlines()) == 3, "got=%s" % have.replace("\n", ","))

    finally:
        say("")
        say("[8] 删临时库")
        rc, _o, err = psql(ADMIN_DB, "DROP DATABASE IF EXISTS %s;" % PROBE_DB)
        chk("DROP DATABASE %s" % PROBE_DB, rc == 0, "rc=%d err=%s" % (rc, err[:160]))

    return bail()


def bail(code=None):
    say("")
    say("=" * 78)
    total = n_pass + n_fail
    say("ASSERTIONS: %d / %d passed   (EXPECTED=%d)" % (n_pass, total, EXPECTED_CHECKS))
    full = (total == EXPECTED_CHECKS)
    if not full:
        say("★ 满额护栏未过：实得 %d 条断言，期望 %d 条 ⇒ 有检查项根本没被执行到"
            % (total, EXPECTED_CHECKS))
    ok = (n_fail == 0) and full
    say("VERDICT: %s" % ("OK -- 修复后等价性成立且新索引真被用上" if ok
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
