# -*- coding: utf-8 -*-
"""Day 33 · 收尾两个券侧索引：`idx_coupons_status` 到底有没有用，
以及 `idx_user_coupons_user_id` 是不是【冗余】。

背景
----
Day 30 的索引体检总表里，只剩一个索引**没定性**：

    idx_coupons_status   ← 有 3 条查询按 status = 1 过滤，但「有调用方」≠「被用上」
                           （Day 29 的 payments(status) 就是反例）→ 判「待测」

本日把它测掉。同时发现**第二个**可疑项：

    idx_user_coupons_user_id  ← Day 30 判它「有效」（UserCouponMapper 有 5 处按 user_id 查）。
    但 09 号补丁给 user_coupons 加了 UNIQUE (user_id, coupon_id)
    ⇒ PG 为此建了唯一索引 uk_user_coupons_user_coupon，
      而它的**第一列就是 user_id** ⇒ 「按 user_id 查」它也能服务。
    ⇒ 单列那个可能是**冗余**的（与 idx_role_permissions_permission_id 同一类问题）。

做法（★ 沿用 Day 31 的 DROP 实验 + 对照组）
------------------------------------------
    阶段 A：索引都在 → 跑 3 条查询，记归一化计划
    阶段 B：DROP 掉 2 个候选 + 1 个对照 → 再跑 → 比计划变不变
    候选：计划【不变】⇒ 没用 / 冗余；对照：计划【必须变】⇒ 证明装置有区分度

★★ 额外做一件 Day 31 没做的事：**同时报两个规模**。
   `coupons` 是张**小表**（真实业务里几十到几百行），
   所以「这个索引有没有用」在真实规模下**根本不重要**。
   ⇒ 只测 2 万行会得出一个**技术上正确、业务上无意义**的结论。
     所以最后把 coupons 缩到 200 行再测一遍，**两个数都报**。
   ★ 判据：样本既不能太小（测不出索引），也不能脱离业务现实（结论没意义）——**两个规模都要看**。

运行：python day33-coupon-status-probe.py
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
PROBE_DB = "mallx_coupon_probe"
SQL_DIR = lp(r"D:\MallX\backend\sql")
REPORT = lp(r"D:\MallX\backend\loadtest\day33-coupon-status-probe-report.txt")

FILES = ["01-schema.sql", "02-index.sql", "03-data.sql", "04-review-constraints.sql",
         "05-admin-permissions.sql", "06-day17-fixtures.sql", "07-admin-permissions.sql",
         "08-marketing-permissions.sql", "09-user-coupons-unique.sql",
         "10-brand-permissions.sql", "11-order-discount.sql", "12-day22-permissions.sql",
         "13-day23-permissions.sql", "14-brand-crud-permissions.sql"]

N_USERS = 5000
N_COUPONS = 20000        # 压力规模（真实券表远小于此）
N_USER_COUPONS = 60000
REAL_COUPONS = 200       # ★ 真实业务规模（几十~几百行）

EXPECTED_CHECKS = 19

lines = []
say = lines.append
n_pass = n_fail = 0
PA = {}
PB = {}
REAL = {}


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

    # ★ status=1 占 95%（低选择性 —— 正是 idx_coupons_status 值不值的核心）
    #   同时让 start/end 覆盖当前时间、received_count < total_count，保证列表查得出来
    ("券 %d 张（status=1 占 95%%）" % N_COUPONS, """
INSERT INTO coupons (name, type, discount_amount, discount_rate, min_amount,
                     total_count, received_count, start_time, end_time, status)
SELECT 'PERF-券-' || g, 'DISCOUNT', 10.00, NULL, 100.00,
       1000, g %% 500,
       CURRENT_TIMESTAMP - interval '10 days',
       CURRENT_TIMESTAMP + interval '10 days',
       CASE WHEN g %% 20 = 0 THEN 0 ELSE 1 END
FROM generate_series(1, %d) g;
""" % N_COUPONS),

    # ★ (user_id, coupon_id) 必须唯一 —— 09 号补丁有 UNIQUE(user_id, coupon_id)
    #   g 从 1..60000：user_id = 1+(g%5000) 取 5000 个值、coupon_id = 1+(g/5000) 取 12 个值
    #   ⇒ 每个用户拿 12 张互不相同的券，组合天然唯一
    ("用户券 %d 条（组合唯一）" % N_USER_COUPONS, """
INSERT INTO user_coupons (user_id, coupon_id, status)
SELECT (SELECT id FROM users ORDER BY id OFFSET (g %% %d) LIMIT 1),
       (SELECT id FROM coupons ORDER BY id OFFSET (g / %d) LIMIT 1),
       'UNUSED'
FROM generate_series(0, %d) g
WHERE (SELECT id FROM coupons ORDER BY id OFFSET (g / %d) LIMIT 1) IS NOT NULL;
""" % (N_USERS, N_USERS, N_USER_COUPONS - 1, N_USERS)),
]

# 阶段 B 要 DROP 的三个索引：2 候选 + 1 对照
DROP_LIST = ["idx_coupons_status",            # 候选 1（Day 30 待测）
             "idx_user_coupons_user_id",      # 候选 2（★ 疑似被 UNIQUE(user_id, coupon_id) 覆盖）
             "idx_user_coupons_coupon_id"]    # 对照（必须被用上）

USER1 = "(SELECT id FROM users ORDER BY id LIMIT 1)"

QUERIES = [
    ("S1", "cand", "idx_coupons_status",
     "C 端可领券列表（status=1 + 时间窗 + 有余量，ORDER BY id DESC）",
     "SELECT id, name, type, discount_amount, min_amount, received_count "
     "FROM coupons WHERE status = 1 "
     "AND start_time <= CURRENT_TIMESTAMP AND end_time >= CURRENT_TIMESTAMP "
     "AND received_count < total_count ORDER BY id DESC LIMIT 10"),

    ("S2", "cand", "idx_user_coupons_user_id",
     "我的券列表（按 user_id，ORDER BY id DESC）",
     "SELECT id, coupon_id, status FROM user_coupons WHERE user_id = %s "
     "ORDER BY id DESC LIMIT 10" % USER1),

    ("S3", "ctrl", "idx_user_coupons_coupon_id",
     "券删除前的引用校验（按 coupon_id count）",
     "SELECT count(*) FROM user_coupons WHERE coupon_id = "
     "(SELECT id FROM coupons ORDER BY id LIMIT 1)"),
]


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
    say("Day 33 -- 券侧索引收尾：idx_coupons_status 有没有用 / user_id 那个是不是冗余")
    say("=" * 78)

    say("")
    say("[0] 建临时库（★ 只动这一个名字，开发库不碰）")
    rc, _o, err = psql(ADMIN_DB, "DROP DATABASE IF EXISTS %s;\nCREATE DATABASE %s;" % (PROBE_DB, PROBE_DB))
    chk("CREATE DATABASE %s" % PROBE_DB, rc == 0, "rc=%d err=%s" % (rc, err[:160]))
    if rc != 0:
        return bail()

    try:
        say("")
        say("[1] 按序灌 01→14（★ 09 号补丁会建 UNIQUE(user_id, coupon_id)）")
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
        say("[4] 规模核对 + ★ 确认 09 号补丁的唯一索引存在（候选 2 的判据前提）")
        n_c = int(one("SELECT count(*) FROM coupons"))
        n_uc = int(one("SELECT count(*) FROM user_coupons"))
        chk("coupons 行数 >= %d" % N_COUPONS, n_c >= N_COUPONS, "actual=%d" % n_c)
        chk("user_coupons 行数 >= %d" % N_USER_COUPONS, n_uc >= N_USER_COUPONS, "actual=%d" % n_uc)
        n_uk = int(one("SELECT count(*) FROM pg_indexes WHERE indexname = "
                       "'uk_user_coupons_user_coupon'"))
        chk("uk_user_coupons_user_coupon 存在（(user_id, coupon_id) 唯一索引）", n_uk == 1,
            "got=%d" % n_uk)

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
        say("[8] ★ 候选：DROP 前后计划必须【不变】")
        for qid, kind, idxname, label, sql in QUERIES:
            if kind != "cand":
                continue
            same = PA[qid]["norm"] == PB[qid]["norm"]
            chk("%s DROP %s 后计划不变" % (qid, idxname), same,
                "A_used=%s B_used=%s" % (PA[qid]["used"], PB[qid]["used"]))
            if not same:
                say("      ---- %s 计划变了：该索引其实有用，不该删 ----" % qid)
                for ln in PB[qid]["raw"].splitlines():
                    say("      " + ln)

        say("")
        say("[9] ★★ 对照：DROP 前后计划必须【发生变化】（证明装置有区分度）")
        for qid, kind, idxname, label, sql in QUERIES:
            if kind != "ctrl":
                continue
            chk("%s DROP %s 后计划确实变了" % (qid, idxname),
                PA[qid]["norm"] != PB[qid]["norm"],
                "A_used=%s B_used=%s" % (PA[qid]["used"], PB[qid]["used"]))

        say("")
        say("[10] ★★ 真实规模复测：coupons 缩到 %d 行（真实业务里就是几十~几百行）" % REAL_COUPONS)
        say("      ★ 只测压力规模会得出「技术上正确、业务上无意义」的结论 —— 两个规模都要报。")
        rc, _o, err = psql(PROBE_DB,
                           "CREATE INDEX IF NOT EXISTS idx_coupons_status ON coupons(status);\n"
                           "DELETE FROM user_coupons;\n"
                           "DELETE FROM coupons WHERE id > %d;\n" % REAL_COUPONS)
        chk("重建 idx_coupons_status + 把 coupons 缩到 %d 行" % REAL_COUPONS, rc == 0,
            "rc=%d err=%s" % (rc, err[:200]))
        rc, _o, err = psql(PROBE_DB, "VACUUM (ANALYZE);")
        chk("缩规模后 VACUUM (ANALYZE)", rc == 0, "err=%s" % err[:160])
        n_real = int(one("SELECT count(*) FROM coupons"))
        chk("coupons 缩到 %d 行" % REAL_COUPONS, n_real <= REAL_COUPONS, "actual=%d" % n_real)

        qid, kind, idxname, label, sql = QUERIES[0]
        rc, out, err = psql(PROBE_DB, "EXPLAIN (ANALYZE, BUFFERS) " + sql)
        rused, rseq = scan_plan(out)
        rm = re.search(r"Execution Time: ([\d.]+) ms", out)
        REAL["S1"] = dict(used=rused, seq=rseq, ms=float(rm.group(1)) if rm else -1.0)
        say("      S1 真实规模：%.3fms  idx=%s seq=%s" % (
            REAL["S1"]["ms"], ",".join(rused) or "-", ",".join(rseq) or "-"))
        chk("真实规模下 S1 耗时 < 5ms（规模小到无所谓）", 0 < REAL["S1"]["ms"] < 5.0,
            "%.3fms" % REAL["S1"]["ms"])

    finally:
        say("")
        say("[11] 删临时库")
        rc, _o, err = psql(ADMIN_DB, "DROP DATABASE IF EXISTS %s;" % PROBE_DB)
        chk("DROP DATABASE %s" % PROBE_DB, rc == 0, "rc=%d err=%s" % (rc, err[:160]))

    return bail()


def bail(code=None):
    say("")
    say("=" * 78)
    say("对照表（A = 索引都在 / B = 已 DROP）")
    say("=" * 78)
    say("      %-4s %-6s %-32s %-10s %-10s %s" % ("ID", "类型", "被 DROP 的索引", "计划变化", "A 耗时", "A 用上的索引"))
    for qid, kind, idxname, label, sql in QUERIES:
        a, b = PA.get(qid), PB.get(qid)
        if not a or not b:
            continue
        say("      %-4s %-6s %-32s %-10s %-10s %s" % (
            qid, "候选" if kind == "cand" else "对照", idxname,
            "变了" if a["norm"] != b["norm"] else "没变",
            "%.2fms" % a["ms"], ",".join(a["used"])[:34] or (",".join(a["seq"]) or "-")))
    if "S1" in REAL:
        say("")
        say("      真实规模（coupons %d 行）：S1 = %.3fms  idx=%s" % (
            REAL_COUPONS, REAL["S1"]["ms"], ",".join(REAL["S1"]["used"]) or "-"))

    total = n_pass + n_fail
    say("")
    say("=" * 78)
    say("ASSERTIONS: %d / %d passed   (EXPECTED=%d)" % (n_pass, total, EXPECTED_CHECKS))
    full = (total == EXPECTED_CHECKS)
    if not full:
        say("★ 满额护栏未过：实得 %d 条断言，期望 %d 条 ⇒ 有检查项根本没被执行到"
            % (total, EXPECTED_CHECKS))
    ok = (n_fail == 0) and full
    say("VERDICT: %s" % ("OK -- 两个候选索引的定性已完成（含真实规模对照）" if ok
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
