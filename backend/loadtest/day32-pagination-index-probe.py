# -*- coding: utf-8 -*-
"""Day 32 · 「分页 + 排序」的索引：单列索引能不能组合？（含偏斜分布的对照实验）

为什么是它
----------
`listMyOrders` 的查询是（`OrderServiceImpl:619-626`）：

    WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?

而 `orders` 上只有两个**单列**索引：`idx_orders_user_id` / `idx_orders_created_at`。
管理端 `listAllOrders` 再叠上可选过滤，变成：

    WHERE status = ? AND user_id = ? ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?

★ 这正是「单列索引组合不起来」的经典形态：
  用 `user_id` 索引筛完还要**排序**；用 `created_at` 索引能免排序但要**扫很多行才凑够过滤条件**。

★★ 但关键在于：**问题只在【偏斜分布】下才显形。**
   本项目 Day 29 造数时 3 万订单均摊给 5000 个用户 = 每人 6 单 ——
   这时**任何**索引都够快，复合索引的收益是 0，测了等于没测。
   真实世界里一定有「一个大买家下了几千单」。
   ⇒ 所以本脚本**故意造出偏斜**：**2 万单归一个 power user**，其余 1 万单摊给 5000 人。
   这正是本项目第 4 条判据「样本必须落在判据的取值域里」的又一次应用。

做法（★ 零副作用）
------------------
临时库 `mallx_page_probe` → 01→14 + 造数（5000 用户 + 3 万订单，**含 1 个 power user**）
→ `VACUUM (ANALYZE)` → 阶段 A 测 4 条查询 → 加两个**候选复合索引** + `VACUUM (ANALYZE)`
→ 阶段 B 重测 → 删库。**开发库零改动、生产 SQL 与索引一行不改。**

★ 判据（沿用 Day 28/29）：
  ① 每个变体都要和基线对**行数**（快而少返回行的改法不是优化，是缺陷）；
  ② 候选索引要被**用上**才算数；
  ③ 同一条 SQL 在**不同 OFFSET** 下分别测 —— 深分页是另一个问题。

运行：python day32-pagination-index-probe.py
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
PROBE_DB = "mallx_page_probe"
SQL_DIR = lp(r"D:\MallX\backend\sql")
REPORT = lp(r"D:\MallX\backend\loadtest\day32-pagination-index-probe-report.txt")

FILES = ["01-schema.sql", "02-index.sql", "03-data.sql", "04-review-constraints.sql",
         "05-admin-permissions.sql", "06-day17-fixtures.sql", "07-admin-permissions.sql",
         "08-marketing-permissions.sql", "09-user-coupons-unique.sql",
         "10-brand-permissions.sql", "11-order-discount.sql", "12-day22-permissions.sql",
         "13-day23-permissions.sql", "14-brand-crud-permissions.sql"]

N_USERS = 5000
N_ORDERS = 30000
N_POWER_ORDERS = 20000      # ★ 偏斜：一个人独占 2 万单（占全库 2/3）
POWER_PCT = 2               # 每 2 单里 1 单归 power user（在 1..N_POWER_ORDERS 区间内）

EXPECTED_CHECKS = 19

lines = []
say = lines.append
n_pass = n_fail = 0
A = {}   # 阶段 A（只有单列索引）
B = {}   # 阶段 B（加了复合索引）


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
    ("维表 %d 用户" % N_USERS, """
INSERT INTO users (username, password, nickname, phone, email, status)
SELECT 'perfuser' || g, 'x', 'PERF', '139' || lpad(g::text, 8, '0'),
       'perf' || g || '@example.com', 1
FROM generate_series(1, %d) g;
""" % N_USERS),

    # ★★ 偏斜分布：前 20000 单全部归 power user（id 最小那个），其余摊给 5000 人。
    #    均摊时（每人 6 单）任何索引都够快，复合索引收益为 0 —— 测不出问题。
    ("订单 %d（★ 前 %d 单归 1 个 power user）" % (N_ORDERS, N_POWER_ORDERS), """
INSERT INTO orders (order_no, user_id, total_amount, pay_amount, status,
                    receiver_name, receiver_phone, receiver_address, created_at, updated_at)
SELECT 'PERF-ORD-' || g,
       CASE WHEN g <= %d
            THEN (SELECT id FROM users ORDER BY id LIMIT 1)
            ELSE (SELECT id FROM users ORDER BY id OFFSET (g %% (SELECT count(*) FROM users)) LIMIT 1)
       END,
       100.00, 100.00,
       CASE WHEN g %% 10 < 8 THEN 'PAID'
            WHEN g %% 10 = 8 THEN 'PENDING_PAYMENT'
            ELSE 'CANCELLED' END,
       'PERF', '13000000000', 'PERF 地址',
       CURRENT_TIMESTAMP - (g || ' minutes')::interval,
       CURRENT_TIMESTAMP - (g || ' minutes')::interval
FROM generate_series(1, %d) g;
""" % (N_POWER_ORDERS, N_ORDERS)),
]

# 候选复合索引（★ 只在临时库里建）
CANDIDATES = """
CREATE INDEX IF NOT EXISTS probe_orders_user_created
    ON orders(user_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS probe_orders_status_created
    ON orders(status, created_at DESC, id DESC);
"""

POWER = "(SELECT id FROM users ORDER BY id LIMIT 1)"
ORDER_BY = "ORDER BY created_at DESC, id DESC"

QUERIES = []   # ★ 在 main 里造完数之后才构造 —— 参数必须用【字面量】，见 build_queries


def build_queries(power_id):
    """★★ 参数必须写成【字面量】，不能用子查询。

    第一版写的是 `user_id = (SELECT id FROM users ORDER BY id LIMIT 1)`，
    计划里那一行是：

        ->  Index Scan using idx_orders_user_id on orders
              Index Cond: (user_id = $0)
              rows=20002            ← 实际读了 2 万行
        而整个 Limit 的估算写的是 `rows=6`

    ⇒ 计划器对**参数**（InitPlan 的 $0）**拿不到统计信息**，只能按默认选择率估成 **6 行**
      （真实 20002 行）。它以为「读 6 行再排序」很便宜，于是选了
      `idx_orders_user_id + Sort`，**我新建的复合索引根本没进入比较**。
    ⇒ 这不是索引的问题，是**我的实验把参数喂错了**：估算失真，计划比较就没有意义。

    ★ 一般化：**凡是把「子查询」当参数喂给 EXPLAIN 的地方，估算都可能失真。**
      Day 27 / 29 / 31 里都有同类写法（`(SELECT id FROM ... LIMIT 1)`），
      它们的结论**没有被推翻**（那几条测的是「单行等值查找用哪个索引」，与行数估算无关），
      但同一个隐患已经记在各自的注释里。
    """
    ob = ORDER_BY
    return [
        ("Q1", "我的订单 第 1 页（power user 2 万单里取 10）",
         "SELECT id, order_no, status, created_at FROM orders "
         "WHERE user_id = %d %s LIMIT 10 OFFSET 0" % (power_id, ob)),
        ("Q2", "我的订单 深分页（OFFSET 5000）",
         "SELECT id, order_no, status, created_at FROM orders "
         "WHERE user_id = %d %s LIMIT 10 OFFSET 5000" % (power_id, ob)),
        ("Q3", "管理端列表：只按 status（PAID 占 80%）",
         "SELECT id, order_no, user_id, created_at FROM orders "
         "WHERE status = 'PAID' %s LIMIT 10 OFFSET 0" % ob),
        ("Q4", "管理端列表：status + user_id（两个过滤叠排序）",
         "SELECT id, order_no, created_at FROM orders "
         "WHERE status = 'PAID' AND user_id = %d %s LIMIT 10 OFFSET 0" % (power_id, ob)),
    ]

# 加索引后「必须用上」的候选
MUST_USE = {
    "Q1": "probe_orders_user_created",
    "Q2": "probe_orders_user_created",
    "Q3": "probe_orders_status_created",
    "Q4": "probe_orders_user_created",
}


def measure(store):
    for qid, label, sql in QUERIES:
        # ★ 正确性指纹：结果行内容（不只是行数）
        val = one("SELECT md5(coalesce(string_agg(t::text, '|' ORDER BY t::text), '')) "
                  "FROM (%s) t" % sql)
        rc, out, err = psql(PROBE_DB, "EXPLAIN (ANALYZE, BUFFERS) " + sql)
        if rc != 0:
            raise RuntimeError("%s EXPLAIN 失败：%s" % (qid, err[:200]))
        idx, seq = scan_plan(out)
        m = re.search(r"Execution Time: ([\d.]+) ms", out)
        ms = float(m.group(1)) if m else -1.0
        store[qid] = dict(val=val, idx=idx, seq=seq, ms=ms, label=label, raw=out)
        say("      %-3s %-9s idx=%-30s seq=%-10s %s" % (
            qid, "%.2fms" % ms, ",".join(idx)[:28] or "-", ",".join(seq) or "-", label[:30]))


def main():
    say("=" * 78)
    say("Day 32 -- 「分页 + 排序」的索引：单列索引组合不起来（临时库 %s）" % PROBE_DB)
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
        say("[2] 造数（★ 故意偏斜：一个人 2 万单）")
        for label, sql in SEEDS:
            rc, _o, err = psql(PROBE_DB, sql)
            chk("造数 %s" % label, rc == 0, "rc=%d err=%s" % (rc, err[:200]))

        say("")
        say("[3] VACUUM (ANALYZE)（★ Day 27 教训：只 ANALYZE 会得到会翻转的结论）")
        rc, _o, err = psql(PROBE_DB, "VACUUM (ANALYZE);")
        chk("基线 VACUUM (ANALYZE)", rc == 0, "err=%s" % err[:160])

        say("")
        say("[4] ★★ 偏斜核对 —— 断言「样本落在判据的取值域里」")
        say("     （均摊时每人 6 单，任何索引都够快，复合索引收益为 0 ⇒ 测了等于没测）")
        n_total = int(one("SELECT count(*) FROM orders"))
        n_power = int(one("SELECT count(*) FROM orders WHERE user_id = %s" % POWER))
        chk("订单总数 >= %d" % N_ORDERS, n_total >= N_ORDERS, "actual=%d" % n_total)
        chk("power user 的订单数 >= %d（★ 分布是偏斜的）" % N_POWER_ORDERS,
            n_power >= N_POWER_ORDERS, "power=%d（占全库 %.0f%%）" % (n_power, 100.0 * n_power / n_total))
        chk("power user 占比 > 50%%（否则偏斜不成立）",
            n_power > n_total * 0.5, "%.0f%%" % (100.0 * n_power / n_total))

        say("")
        say("[4b] ★ 参数改用【字面量】—— 这是本脚本第一版失败的地方")
        global QUERIES
        power_id = int(one("SELECT id FROM users ORDER BY id LIMIT 1"))
        QUERIES = build_queries(power_id)
        say("     power user id = %d，写进 SQL 字面量。" % power_id)
        say("     第一版用子查询当参数 ⇒ 计划器拿不到统计信息，把 20002 行估成 6 行")
        say("     ⇒ 计划比较完全失真（新建的复合索引根本没进入比较）。")
        say("     ★ 这是【我的实验装置的错】，不是索引的错 —— 见 build_queries 的注释。")

        say("")
        say("[5] 阶段 A —— 只有单列索引（idx_orders_user_id / idx_orders_created_at）")
        measure(A)

        say("")
        say("[6] 阶段 B —— 加两个候选复合索引 + VACUUM (ANALYZE)")
        say("     候选：probe_orders_user_created(user_id, created_at DESC, id DESC)")
        say("           probe_orders_status_created(status, created_at DESC, id DESC)")
        rc, _o, err = psql(PROBE_DB, CANDIDATES)
        chk("建候选复合索引", rc == 0, "rc=%d err=%s" % (rc, err[:200]))
        rc, _o, err = psql(PROBE_DB, "VACUUM (ANALYZE);")
        chk("加索引后 VACUUM (ANALYZE)", rc == 0, "err=%s" % err[:160])

        say("")
        say("[7] 阶段 B —— 重测")
        measure(B)

        say("")
        say("[8] ★ 加索引不能改数：4 条查询的返回值必须逐值相等")
        for qid, _l, _s in QUERIES:
            chk("%s 返回值不变" % qid, A[qid]["val"] == B[qid]["val"],
                "A=%s B=%s" % (A[qid]["val"][:12], B[qid]["val"][:12]))

        say("")
        say("[9] ★ 候选复合索引是否真被用上")
        for qid, want in MUST_USE.items():
            ok = want in B[qid]["idx"]
            chk("%s 用上 %s" % (qid, want), ok, "idx=%s" % B[qid]["idx"])
            if not ok:
                # ★ 未命中必须留下【完整计划】作为证据，否则解释只能是猜的
                say("")
                say("      ---- %s 未命中：阶段 B 完整计划 ----" % qid)
                for ln in B[qid]["raw"].splitlines():
                    say("      " + ln)
                say("      ---- %s 计划结束 ----" % qid)
                say("")

        say("")
        say("[10] ★ 单列索引的局限：阶段 A 里这几条查询有没有免掉排序")
        for qid, _l, _s in QUERIES:
            a = A[qid]
            say("      %-3s A: idx=%-30s seq=%-8s %s" % (
                qid, ",".join(a["idx"])[:28] or "-", ",".join(a["seq"]) or "-", "%.2fms" % a["ms"]))

        say("")
        say("[10b] ★★ 探针：深分页的真解不是「加索引」，是【换分页方式】")
        say("      OFFSET 的成本是 O(offset) —— 加索引只能改常数因子，改不了量级。")
        say("      游标式（keyset）分页把 OFFSET 换成「从上次的位置往后取」，成本与深度无关。")
        say("      ⚠️ 游标值同样必须用【字面量】喂进去（同一个教训）。")
        # 先取第 5000 行那条记录的 (created_at, id) 作为游标
        cur = one("SELECT to_char(created_at, 'YYYY-MM-DD HH24:MI:SS.US') || '|' || id "
                  "FROM orders WHERE user_id = %d ORDER BY created_at DESC, id DESC "
                  "OFFSET 5000 LIMIT 1" % power_id)
        ts, cid = cur.split("|")
        keyset = ("SELECT id, order_no, status, created_at FROM orders "
                  "WHERE user_id = %d AND (created_at, id) < (TIMESTAMP '%s', %d) "
                  "ORDER BY created_at DESC, id DESC LIMIT 10" % (power_id, ts, int(cid)))
        rc, out, err = psql(PROBE_DB, "EXPLAIN (ANALYZE, BUFFERS) " + keyset)
        if rc != 0:
            say("      [WARN] keyset 探针 EXPLAIN 失败：%s" % err[:160])
        else:
            kidx, kseq = scan_plan(out)
            km = re.search(r"Execution Time: ([\d.]+) ms", out)
            kms = float(km.group(1)) if km else -1.0
            say("      keyset（从第 5000 行之后取 10 条）：%s  idx=%s" % (
                "%.2fms" % kms, ",".join(kidx) or (",".join(kseq) or "-")))
            say("      对比 OFFSET 5000（阶段 B）：%.2fms  ⇒ 相差 %.0f 倍" % (
                B["Q2"]["ms"], (B["Q2"]["ms"] / kms) if kms > 0 else 0))

    finally:
        say("")
        say("[11] 删临时库")
        rc, _o, err = psql(ADMIN_DB, "DROP DATABASE IF EXISTS %s;" % PROBE_DB)
        chk("DROP DATABASE %s" % PROBE_DB, rc == 0, "rc=%d err=%s" % (rc, err[:160]))

    return bail()


def bail(code=None):
    say("")
    say("=" * 78)
    say("对照表（A = 只有单列索引 / B = 加了复合索引）")
    say("=" * 78)
    say("      %-4s %-10s %-10s %-7s %s" % ("ID", "A 耗时", "B 耗时", "提升", "B 用上的索引"))
    for qid, label, sql in QUERIES:
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
    say("VERDICT: %s" % ("OK -- 复合索引的收益与「不改数」都已取证" if ok
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
