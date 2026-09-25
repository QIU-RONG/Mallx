# -*- coding: utf-8 -*-
"""Day 29 · 管理端 / Dashboard 聚合查询的索引审计（含「加索引值不值」的对照实验）。

为什么是它
----------
Day 27 审的是**商品侧**的 13 条查询。管理端与 Dashboard 从没被审过 ——
而它们恰恰是**聚合 + 日期过滤**（最容易慢的一类），且 `DashboardMapper.xml` 的
5 条查询里有 2 条直接打在 `payments` 上：

    sumPaidAmount   : SELECT coalesce(sum(amount),0) FROM payments WHERE status = 'SUCCESS'
    selectDailyTrend: ... FROM payments WHERE status='SUCCESS' AND paid_at >= CAST(? AS date) GROUP BY 1

★ 而 `02-index.sql` 里 `payments` **只有** `idx_payments_order_id` ——
  `status` 与 `paid_at` 上**一个索引都没有**。所以这两条查询只能全表扫。

做法（★ 零副作用）：临时库 `mallx_dash_probe` → 01→14 + 造数（orders 3 万 / payments 3 万）
→ `VACUUM (ANALYZE)` → **阶段 A** 记录基线计划 → **阶段 B** 加上候选索引 + `VACUUM (ANALYZE)`
→ 重测 → 删库。**开发库零改动、生产 SQL 与索引一行不改。**

★ 两个判据（沿用 Day 28 的做法）：
  ① **对照实验**：光说「全表扫」没用，要说「加上这个索引之后变成什么、快多少」；
  ② **加索引不能改数**：5 条查询的返回值必须在加索引前后**逐值相等**，
     否则那不是优化，是把口径改坏了。

★ 不做的：`count(*)` 全表计数（D1–D3）只**记录不断言** ——
  PG 里全表 count 天生 O(n)，加任何索引都消不掉，断言它只会得到一条假结论。
  这一类属于「已知边界」，不是缺陷。

运行：python day29-dashboard-explain-audit.py
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
PROBE_DB = "mallx_dash_probe"
SQL_DIR = lp(r"D:\MallX\backend\sql")
REPORT = lp(r"D:\MallX\backend\loadtest\day29-dashboard-explain-audit-report.txt")

FILES = ["01-schema.sql", "02-index.sql", "03-data.sql", "04-review-constraints.sql",
         "05-admin-permissions.sql", "06-day17-fixtures.sql", "07-admin-permissions.sql",
         "08-marketing-permissions.sql", "09-user-coupons-unique.sql",
         "10-brand-permissions.sql", "11-order-discount.sql", "12-day22-permissions.sql",
         "13-day23-permissions.sql", "14-brand-crud-permissions.sql"]

N_CATEGORIES = 300
N_USERS = 5000
N_PRODUCTS = 30000
N_ORDERS = 30000
# ★ SUCCESS 占 95%（低选择性）—— 这是 payment 的**真实**分布：
#   失败单是少数。低选择性正是「status 单列索引值不值」这个问题的核心。
FAILED_PCT = 20

EXPECTED_CHECKS = 20

lines = []
say = lines.append
n_pass = n_fail = 0
A = {}   # 阶段 A（基线）
B = {}   # 阶段 B（加索引后）


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

    ("维表 %d 用户" % N_USERS, """
INSERT INTO users (username, password, nickname, phone, email, status)
SELECT 'perfuser' || g, 'x', 'PERF', '139' || lpad(g::text, 8, '0'),
       'perf' || g || '@example.com', 1
FROM generate_series(1, %d) g;
""" % N_USERS),

    ("商品 %d（全部未删）" % N_PRODUCTS, """
INSERT INTO products (category_id, brand_id, name, subtitle, description, main_image, status, is_deleted)
SELECT (SELECT id FROM categories ORDER BY id OFFSET (g %% (SELECT count(*) FROM categories)) LIMIT 1),
       (SELECT id FROM brands ORDER BY id OFFSET (g %% GREATEST((SELECT count(*) FROM brands),1)) LIMIT 1),
       'PERF-商品-' || g, 'PERF-副标题', 'PERF-描述', '/img/perf-' || g || '.jpg', 1, 0
FROM generate_series(1, %d) g;
""" % N_PRODUCTS),

    # created_at 铺开在 ~20 天里（3 万分钟），这样 selectDailyTrend 的日期过滤才有区分度
    ("订单 %d（created_at 铺开 20 天）" % N_ORDERS, """
INSERT INTO orders (order_no, user_id, total_amount, pay_amount, status,
                    receiver_name, receiver_phone, receiver_address, created_at, updated_at)
SELECT 'PERF-ORD-' || g,
       (SELECT id FROM users ORDER BY id OFFSET (g %% (SELECT count(*) FROM users)) LIMIT 1),
       100.00, 100.00, 'PAID', 'PERF', '13000000000', 'PERF 地址',
       CURRENT_TIMESTAMP - (g || ' minutes')::interval,
       CURRENT_TIMESTAMP - (g || ' minutes')::interval
FROM generate_series(1, %d) g;
""" % N_ORDERS),

    # ★ payments 是本次的主角：status 95% 为 SUCCESS（低选择性），paid_at 铺开
    ("支付 %d（SUCCESS 95%%，paid_at 铺开）" % N_ORDERS, """
INSERT INTO payments (payment_no, order_id, amount, method, status, paid_at, created_at)
SELECT 'PERF-PAY-' || o.rn, o.id, 100.00, 'ALIPAY',
       CASE WHEN o.rn %% %d = 0 THEN 'FAILED' ELSE 'SUCCESS' END,
       o.created_at + interval '5 minutes',
       o.created_at + interval '5 minutes'
FROM (SELECT id, created_at, row_number() OVER (ORDER BY id) rn
        FROM orders WHERE order_no LIKE 'PERF-%%') o;
""" % FAILED_PCT),
]

# 候选索引（★ 只在临时库里建；不是本次要提交的东西）
CANDIDATES = """
CREATE INDEX IF NOT EXISTS probe_payments_status         ON payments(status);
CREATE INDEX IF NOT EXISTS probe_payments_status_paid_at ON payments(status, paid_at);
"""

# ------------------------------------------------------------------ 查询集
# 期望："INDEX:<名>" 加索引后必须出现 / "SEQ:<表>" 加索引后必须仍是全表扫
DASH = {
    "D1": ("countUsers 全表计数（★ 已知边界，只记录）",
           "SELECT count(*) FROM users"),
    "D2": ("countProducts（is_deleted = 0，★ 已知边界，只记录）",
           "SELECT count(*) FROM products WHERE is_deleted = 0"),
    "D3": ("countOrders 全表计数（★ 已知边界，只记录）",
           "SELECT count(*) FROM orders"),
    "D4": ("sumPaidAmount（status = 'SUCCESS'）",
           "SELECT coalesce(sum(amount), 0) FROM payments WHERE status = 'SUCCESS'"),
    "D5": ("selectDailyTrend（日期骨架 LEFT JOIN 两个聚合）",
           """WITH days AS (
                SELECT to_char(d, 'YYYY-MM-DD') AS date
                FROM generate_series(CAST(CURRENT_DATE - 7 AS date), CURRENT_DATE, INTERVAL '1 day') AS d
              ),
              o AS (
                SELECT to_char(created_at, 'YYYY-MM-DD') AS date, count(*) AS cnt
                FROM orders WHERE created_at >= CAST(CURRENT_DATE - 7 AS date) GROUP BY 1
              ),
              p AS (
                SELECT to_char(paid_at, 'YYYY-MM-DD') AS date, sum(amount) AS amt
                FROM payments
                WHERE status = 'SUCCESS' AND paid_at >= CAST(CURRENT_DATE - 7 AS date) GROUP BY 1
              )
              SELECT days.date, coalesce(o.cnt, 0) AS order_count, coalesce(p.amt, 0) AS sales_amount
              FROM days LEFT JOIN o ON o.date = days.date LEFT JOIN p ON p.date = days.date
              ORDER BY days.date"""),
}

# 加索引后「必须用上」的断言
MUST_USE_AFTER = {
    "D5": "probe_payments_status_paid_at",
}
# ★ 加索引后「仍然不该被用上」——低选择性索引（status='SUCCESS' 占 95%），
#   反向对照。第一版这里写的是「必须用上」，实测被否掉了：加完索引计划器照样全表扫，
#   而且耗时没变（10.12ms → 10.77ms）。**那是计划器对，不是索引没建好。**
MUST_NOT_USE_AFTER = {
    "D4": "probe_payments_status",
}


def measure(tag, store):
    for qid, (label, sql) in DASH.items():
        val = one("SELECT md5(coalesce(string_agg(t::text, '|' ORDER BY t::text), '')) "
                  "FROM (%s) t" % sql)
        rc, out, err = psql(PROBE_DB, "EXPLAIN (ANALYZE, BUFFERS) " + sql)
        idx, seq = scan_plan(out) if rc == 0 else ([], [])
        m = re.search(r"Execution Time: ([\d.]+) ms", out)
        ms = float(m.group(1)) if m else -1.0
        store[qid] = dict(label=label, val=val, idx=idx, seq=seq, ms=ms)
        say("      %-3s %-9s idx=%-34s seq=%-16s %s" % (
            qid, "%.2fms" % ms, ",".join(idx)[:32] or "-",
            ",".join(seq) or "-", label[:26]))
    return store


def main():
    say("=" * 78)
    say("Day 29 -- 管理端 / Dashboard 聚合查询的索引审计（临时库 %s）" % PROBE_DB)
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
        say("[4] 规模核对")
        for tbl, want in [("orders", N_ORDERS), ("payments", N_ORDERS)]:
            got = int(one("SELECT count(*) FROM %s" % tbl))
            chk("%s 行数 >= %d" % (tbl, want), got >= want, "actual=%d" % got)

        say("")
        say("[5] 阶段 A —— 基线（payments 上只有 idx_payments_order_id）")
        measure("A", A)

        say("")
        say("[6] 阶段 B —— 加上候选索引 + VACUUM (ANALYZE)")
        say("     候选：probe_payments_status(status) / probe_payments_status_paid_at(status, paid_at)")
        rc, _o, err = psql(PROBE_DB, CANDIDATES)
        chk("建候选索引", rc == 0, "rc=%d err=%s" % (rc, err[:200]))
        rc, _o, err = psql(PROBE_DB, "VACUUM (ANALYZE);")
        chk("加索引后 VACUUM (ANALYZE)", rc == 0, "err=%s" % err[:160])

        say("")
        say("[7] 阶段 B —— 重测")
        measure("B", B)

        say("")
        say("[8] ★ 加索引不能改数：5 条查询的返回值必须逐值相等")
        for qid in DASH:
            chk("%s 返回值不变" % qid, A[qid]["val"] == B[qid]["val"],
                "A=%s B=%s" % (A[qid]["val"][:12], B[qid]["val"][:12]))

        say("")
        say("[9] ★ 候选索引是否真被用上")
        for qid, want in MUST_USE_AFTER.items():
            chk("%s 加索引后用上 %s" % (qid, want), want in B[qid]["idx"],
                "idx=%s" % B[qid]["idx"])
        for qid, want in MUST_NOT_USE_AFTER.items():
            chk("%s 加索引后【仍然不该】用 %s（低选择性，计划器应当绕开）" % (qid, want),
                want not in B[qid]["idx"], "idx=%s" % B[qid]["idx"])

        say("")
        say("[10] ★ 全表 count 只记录不断言（PG 里 O(n) 消不掉，断言它只会得到假结论）")
        for qid in ("D1", "D2", "D3"):
            say("      %s  A=%.2fms  B=%.2fms   （加索引前后都全表扫，属已知边界）"
                % (qid, A[qid]["ms"], B[qid]["ms"]))

    finally:
        say("")
        say("[11] 删临时库")
        rc, _o, err = psql(ADMIN_DB, "DROP DATABASE IF EXISTS %s;" % PROBE_DB)
        chk("DROP DATABASE %s" % PROBE_DB, rc == 0, "rc=%d err=%s" % (rc, err[:160]))

    return bail()


def bail(code=None):
    say("")
    say("=" * 78)
    say("对照表（A = 基线 / B = 加候选索引后）")
    say("=" * 78)
    say("      %-4s %-10s %-10s %-7s %s" % ("ID", "A 耗时", "B 耗时", "提升", "B 用上的索引"))
    for qid in ("D1", "D2", "D3", "D4", "D5"):
        a, b = A.get(qid), B.get(qid)
        if not a or not b:
            continue
        gain = ("%.1fx" % (a["ms"] / b["ms"])) if b["ms"] > 0 else "-"
        say("      %-4s %-10s %-10s %-7s %s" % (
            qid, "%.2fms" % a["ms"], "%.2fms" % b["ms"], gain,
            ",".join(b["idx"])[:40] or (",".join(b["seq"]) or "-")))

    total = n_pass + n_fail
    say("")
    say("=" * 78)
    say("ASSERTIONS: %d / %d passed   (EXPECTED=%d)" % (n_pass, total, EXPECTED_CHECKS))
    full = (total == EXPECTED_CHECKS)
    if not full:
        say("★ 满额护栏未过：实得 %d 条断言，期望 %d 条 ⇒ 有检查项根本没被执行到"
            % (total, EXPECTED_CHECKS))
    ok = (n_fail == 0) and full
    say("VERDICT: %s" % ("OK -- 候选索引的效果与「不改数」都已取证" if ok
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
