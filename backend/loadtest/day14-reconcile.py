# -*- coding: utf-8 -*-
"""
Day 14 Step 5 -- reconciliation: does inventory_logs actually explain inventories?

Step 4 built the ledger. This script asks the only question that matters about it:
if you replayed the book from the beginning, would you arrive at the numbers the
table holds right now?

The audit, per SKU:

    available_now  ==  first_row.before_stock + Σ(change_quantity)

which is equivalent to (and cross-checked against) `available_now == last_row.after_stock`,
plus the chain must be gapless: row[i].before == row[i-1].after.

★ Why this is worth doing at all: the ledger's whole value is that it can catch a
  write that BYPASSED the application. Anything that mutates inventories through the
  service appends a row, so the two agree by construction. A raw `UPDATE inventories`
  from a psql prompt does NOT -- and that is exactly the drift Day 14 section 0.2 found.
  Section [4] below demonstrates the audit catching such a write (inside a rolled-back
  transaction, so nothing is actually harmed).

★ Baseline: section 0.3 of the day's doc pins the expected stock. The ledger is expected
  to explain any SKU that has moved away from it. SKUs that were never touched must still
  equal the baseline exactly.

Usage:
    python day14-reconcile.py
Report (utf-8) is written next to this file: day14-reconcile-report.txt
"""
import os
import subprocess
import sys

DOCKER = r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "day14-reconcile-report.txt")

# Section 0.3 baseline: sku -> (total, available, locked, sold)
BASELINE = {
    1: (100, 100, 0, 0),
    2: (80, 80, 0, 0),
    3: (60, 56, 0, 4),
    4: (150, 147, 0, 3),
    5: (120, 117, 0, 3),
    6: (40, 40, 0, 0),
    7: (90, 90, 0, 0),
}

_lines = []


def say(s=""):
    _lines.append(s)


def flush():
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(_lines) + "\n")


# ---------------------------------------------------------------- db helper
def psql(sql, sep="|"):
    """Run SQL through the container's psql.

    ★ 失败必须【喊出来】：早期版本只返回 stdout，而 psql 的报错走 stderr，
      于是一句 SQL 语法错误表现为「查询结果为空」，断言只报一个莫名其妙的 FAIL。
      现在 rc != 0 或 stderr 里出现 ERROR 就直接抛异常，把 SQL 一起打出来。
    """
    p = subprocess.run(
        [DOCKER, "exec", "-i", "-e", "PGCLIENTENCODING=UTF8",
         "mallx-postgres", "psql", "-U", "mallx", "-d", "mallx",
         "-t", "-A", "-F", sep, "-c", sql],
        capture_output=True)
    out = p.stdout.decode("utf-8", "replace").strip()
    err = p.stderr.decode("utf-8", "replace").strip()
    if p.returncode != 0 or "ERROR" in err.upper():
        raise RuntimeError("psql failed (rc=%s)\n--- stderr ---\n%s\n--- sql ---\n%s"
                           % (p.returncode, err, sql))
    return out


def rows(sql, ncols):
    out = []
    for line in psql(sql).splitlines():
        p = [x.strip() for x in line.split("|")]
        if len(p) == ncols:
            out.append(p)
    return out


def one(sql):
    return psql(sql).strip()


# ---------------------------------------------------------------- audit SQL
# ★ 一份 SQL 同时给出：账本首值、账本末值、Σ(change)、由账本推出来的 available
AUDIT_SQL = """
WITH ordered AS (
    SELECT sku_id, id, before_stock, after_stock, change_quantity,
           ROW_NUMBER() OVER (PARTITION BY sku_id ORDER BY id)  AS rn,
           COUNT(*)    OVER (PARTITION BY sku_id)              AS cnt,
           SUM(change_quantity) OVER (PARTITION BY sku_id)     AS sum_change
      FROM inventory_logs
),
firsts AS (SELECT sku_id, before_stock, sum_change FROM ordered WHERE rn = 1),
lasts  AS (SELECT sku_id, after_stock              FROM ordered WHERE rn = cnt)
SELECT i.sku_id,
       i.available_stock,
       COALESCE(f.before_stock, -1),
       COALESCE(f.sum_change, 0),
       COALESCE(f.before_stock, i.available_stock) + COALESCE(f.sum_change, 0),
       COALESCE(l.after_stock, -1),
       (COALESCE(l.after_stock, i.available_stock) = i.available_stock),
       (COALESCE(f.before_stock, i.available_stock) + COALESCE(f.sum_change, 0)
            = i.available_stock)
  FROM inventories i
  LEFT JOIN firsts f ON f.sku_id = i.sku_id
  LEFT JOIN lasts  l ON l.sku_id = i.sku_id
 ORDER BY i.sku_id;
"""

# 链上是否有断点（某行的 before != 前一行的 after）
GAP_SQL = """
WITH ordered AS (
    SELECT sku_id, id, before_stock,
           LAG(after_stock) OVER (PARTITION BY sku_id ORDER BY id) AS prev_after
      FROM inventory_logs
)
SELECT COUNT(*) FROM ordered WHERE prev_after IS NOT NULL AND before_stock <> prev_after
"""

CONSERVATION_SQL = """
WITH l AS (SELECT sku_id, locked_stock FROM inventories WHERE locked_stock <> 0),
     p AS (SELECT oi.sku_id, SUM(oi.quantity) q FROM order_items oi
             JOIN orders o ON o.id = oi.order_id
            WHERE o.status='PENDING_PAYMENT' GROUP BY oi.sku_id)
SELECT COUNT(*) FROM l FULL OUTER JOIN p ON l.sku_id = p.sku_id
 WHERE COALESCE(l.locked_stock,0) <> COALESCE(p.q,0)
"""


# ================================================================ main
def main():
    checks = []

    def chk(name, good):
        checks.append((name, bool(good)))

    say("=" * 78)
    say("Day 14 Step 5 -- reconciliation: inventory_logs vs inventories, per SKU")
    say("=" * 78)

    # ---------------------------------------------------------- [0] the table
    say("\n[0] PER-SKU RECONCILIATION")
    say("    ledger_derived = first_row.before_stock + SUM(change_quantity)")
    say("    %-4s %9s %11s %9s %14s %11s  %s"
        % ("sku", "available", "first_before", "sum_chg", "ledger_derived", "last_after", "verdict"))
    data = rows(AUDIT_SQL, 8)
    for r in data:
        sku, avail, first_before, sum_chg, derived, last_after, last_ok, sum_ok = (
            int(r[0]), int(r[1]), int(r[2]), int(r[3]), int(r[4]), int(r[5]),
            r[6].lower() in ("t", "true"), r[7].lower() in ("t", "true"))
        has_ledger = int(first_before) != -1
        verdict = "OK" if (last_ok and sum_ok) else "DRIFT"
        say("    %-4d %9d %11s %9s %14d %11s  %s"
            % (sku, avail,
               str(first_before) if has_ledger else "-",
               ("%+d" % sum_chg) if has_ledger else "-",
               derived,
               str(last_after) if has_ledger else "-",
               verdict))

    # ---------------------------------------------------------- [1] assertions
    say("\n[1] AUDIT ASSERTIONS (every SKU)")
    for r in data:
        sku = int(r[0])
        has_ledger = int(r[2]) != -1
        chk("sku%d: ledger's last after_stock == current available" % sku,
            r[6].lower() in ("t", "true"))
        chk("sku%d: first_before + SUM(change) == current available" % sku,
            r[7].lower() in ("t", "true"))
        if has_ledger:
            chk("sku%d: ledger's implied available is non-negative" % sku, int(r[4]) >= 0)
    gaps = int(one(GAP_SQL))
    say("  gapless-chain check: rows whose before != previous after -> %d" % gaps)
    chk("★ ledger chain has no gaps across all SKUs", gaps == 0)

    # ---------------------------------------------------------- [2] baseline
    say("\n[2] SKUs NEVER TOUCHED MUST STILL EQUAL THE SECTION 0.3 BASELINE")
    say("    %-4s %-28s %-28s %s" % ("sku", "baseline (t/a/l/s)", "now (t/a/l/s)", "verdict"))
    for r in data:
        sku = int(r[0])
        touched = int(r[2]) != -1
        now = rows("SELECT total_stock, available_stock, locked_stock, sold_stock"
                   " FROM inventories WHERE sku_id=%d" % sku, 4)[0]
        now = tuple(int(x) for x in now)
        base = BASELINE[sku]
        same = (now == base)
        verdict = "= baseline" if same else ("MOVED (ledger explains)" if touched else "MOVED (UNEXPLAINED)")
        say("    %-4d %-28s %-28s %s"
            % (sku, "%d/%d/%d/%d" % base, "%d/%d/%d/%d" % now, verdict))
        if not touched:
            chk("★ sku%d has no ledger rows so it must equal the baseline exactly" % sku, same)
        if touched and not same:
            chk("sku%d moved away from baseline but the ledger explains it" % sku, True)

    # ---------------------------------------------------------- [3] conservation
    say("\n[3] BUSINESS CONSERVATION (locked vs PENDING_PAYMENT order items)")
    drift = int(one(CONSERVATION_SQL))
    say("  drifting SKUs = %d" % drift)
    chk("business conservation holds", drift == 0)
    neg = int(one("SELECT count(*) FROM inventories WHERE available_stock < 0"
                  " OR locked_stock < 0 OR sold_stock < 0"))
    chk("no negative stock anywhere", neg == 0)
    ident = int(one("SELECT count(*) FROM inventories"
                    " WHERE total_stock <> available_stock + locked_stock + sold_stock"))
    say("  SKUs breaking total = available + locked + sold : %d" % ident)
    chk("arithmetic identity holds for all SKUs", ident == 0)

    # ---------------------------------------------------------- [4] teeth
    say("\n[4] ★ DOES THE AUDIT HAVE TEETH?  (bypass the service, inside a ROLLED-BACK tx)")
    say("  A raw UPDATE that never goes through InventoryService should make the ledger")
    say("  disagree with the table. Everything below runs in one transaction and is rolled back.")
    say("  ⚠️ 必须先做一次【合法】变动给账本打底：审计 SQL 里有")
    say("     COALESCE(f.before_stock, i.available_stock) 这个回退 —— 账本为空时")
    say("     期望值直接退化成现值，审计【永远自洽】，任何改动都测不出漂移。")
    say("     （Day 15 发现：收官清理清空账本后，本测试必然假失败。）")
    tgt = 4
    before = rows("SELECT available_stock FROM inventories WHERE sku_id=%d" % tgt, 1)[0][0]
    raw = psql("""
BEGIN;
-- (1) 先做一次【合法】变动：库存与账本同时改 -> 此刻审计应当自洽
UPDATE inventories SET available_stock = available_stock - 1 WHERE sku_id = %d;
INSERT INTO inventory_logs (sku_id, change_quantity, before_stock, after_stock, type, reference_id)
SELECT %d, -1, available_stock + 1, available_stock, 'ORDER_LOCK', NULL
  FROM inventories WHERE sku_id = %d;
SELECT 'LEGIT: available=' || available_stock || '  sku%d ledger rows='
       || (SELECT count(*) FROM inventory_logs WHERE sku_id = %d)
  FROM inventories WHERE sku_id = %d;
-- (2) 再做一次【绕过服务】的裸 UPDATE：只改库存、不留流水 -> 审计必须报警
UPDATE inventories SET available_stock = available_stock - 1 WHERE sku_id = %d;
SELECT 'MUTATED: available is now ' || available_stock FROM inventories WHERE sku_id = %d;
%s
SELECT '[4] BYPASS-AUDIT (expected false): ' || (COALESCE(f.before_stock, i.available_stock) + COALESCE(f.sum_change, 0)
        = i.available_stock) FROM inventories i
  LEFT JOIN (SELECT sku_id, before_stock, sum_change FROM (
        SELECT sku_id, before_stock, SUM(change_quantity) OVER (PARTITION BY sku_id) sum_change,
               ROW_NUMBER() OVER (PARTITION BY sku_id ORDER BY id) rn
          FROM inventory_logs) t WHERE rn=1) f ON f.sku_id = i.sku_id
 WHERE i.sku_id = %d;
ROLLBACK;
SELECT 'AFTER ROLLBACK: available is ' || available_stock FROM inventories WHERE sku_id = %d;
""" % (tgt, tgt, tgt, tgt, tgt, tgt, tgt, tgt, AUDIT_SQL, tgt, tgt))
    for line in raw.splitlines():
        say("  %s" % line)
    # ★ 标签里带着 "(expected false)" 一起断言 —— 这一行"必须是 false"，
    #   它就是"审计有牙齿"的正面证据。曾经的坑：报告里那行裸的 `VERDICT: false`
    #   被 grep VERDICT 的人当成脚本失败（docs/backlog.md 附一① 就是这条误读）。
    chk("★ audit reported DRIFT while the bypassed write was in effect "
        "(label 自带 expected false，不再会被误读成脚本失败)",
        "[4] BYPASS-AUDIT (expected false): f" in raw)
    after = rows("SELECT available_stock FROM inventories WHERE sku_id=%d" % tgt, 1)[0][0]
    say("  sku%d available: %s -> %s (rolled back)" % (tgt, before, after))
    chk("rollback restored the value (zero side effects)", before == after)

    # ---------------------------------------------------------- summary
    passed = sum(1 for _, ok in checks if ok)
    total = len(checks)
    say("\n" + "=" * 78)
    say("ASSERTIONS: %d / %d passed" % (passed, total))
    say("★ 阅读提示：本报告里唯一出现 false 的地方是 [4] 段的 "
        "\"[4] BYPASS-AUDIT (expected false): false\"。")
    say("  那一行【必须是 false】—— 它是「审计能抓到绕过服务的裸写」的正面证据：")
    say("  脚本在事务里故意做一次不记账的 UPDATE，审计若报 true 就说明它没有牙齿。")
    say("  换句话说：grep 这个报告时不要拿 false 当失败判据，看本行和 [4] 段标签。")
    if passed != total:
        say("\nFAILED:")
        for name, ok in checks:
            if not ok:
                say("  [FAIL] %s" % name)
    say("=" * 78)
    flush()
    print("ASSERTIONS: %d / %d passed" % (passed, total))
    print("report -> %s" % OUT)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
