# -*- coding: utf-8 -*-
"""
Day 17 Step 0 -- M1 milestone regression (place -> pay -> ship -> confirm -> review).

Why this exists
---------------
Day 12..16 each proved its own step and wrote its own report. Milestone M1 "closed"
when Day 16 hit 75/75 -- but "every part passed on its own day" is NOT the same claim
as "the whole chain still passes today, on the current build".

So this script does NOT re-implement the chain. It reads the three chain scripts'
OWN reports (proving they were regenerated in this run) and brackets them with a
database snapshot, turning the milestone claim into three checkable things:

    (a) every link is all-green,
    (b) the database is exactly where it started, and
    (c) the milestone invariants all hold.

Why it is a collector instead of a runner
-----------------------------------------
★ This machine is commit-limited (32 GB RAM, 8 GB pagefile, commit limit ~40 GB,
  already ~34 GB used by IDEA + WSL + the IDE + this agent). Spawning a Python
  from a Python to spawn `docker exec` from that tripped WinError 1455
  ("page file too small") -- not a bug in the chain, a bug in the harness.
  ★★ Design rule learned: **the harness must not nest heavy child processes on a
  commit-limited box.** Run the chain scripts one at a time from the shell, then
  run this collector -- it only fans out to `psql`, the cheapest child we have.

Usage
-----
    1)  python day17-m1-regression.py --baseline      # snapshot BEFORE the chain
    2)  run the five listed scripts one at a time, from the shell
        (3 chain links + 2 read-side checks -- see RUNS)
    3)  python day17-m1-regression.py                 # collect + compare + verdict

Step 1 writes day17-m1-baseline.json and day17-m1-stamp.txt; step 3 uses the stamp
to prove each report was regenerated AFTER the stamp (i.e. by this run, not a stale
file from last week).

Repeatable: yes. All five scripts are self-cleaning (the read-side pair only reads),
so this whole sequence can be run any time and leaves the database where it found it.

★★ T2 (fixed on Day 24) -- why the read-side pair was added
----------------------------------------------------------
The list used to hold only day14 / day15 / day16. That left a real regression
blind spot, and Day 22 walked straight into it: adding ``discountAmount`` to
``OrderDetailVO``/``OrderVO`` broke ``day17-a`` and ``day17-b`` (they assert the
field set with a two-way ``set(keys()) == set(FIELDS)`` comparison -- one missing
field FAILs, one extra field FAILs) -- and **no automated regression complained**,
because neither script was on this list.

★ Generalised rule: "every part passed on its own day" and "the whole surface still
  checks out today" are different claims. A milestone list that only covers the
  happy-path chain silently stops covering anything that gets added beside it.
  ⇒ When a new endpoint/VO is added next to an existing milestone, ask whether the
  new surface has a home in the milestone list, not just whether it has a script.
"""
import json
import os
import re
import subprocess
import sys
import time

DOCKER = r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "day17-m1-regression-report.txt")
BASELINE = os.path.join(HERE, "day17-m1-baseline.json")
STAMP = os.path.join(HERE, "day17-m1-stamp.txt")

# ---------------------------------------------------------------- the list
# kind: "chain" = an actual link of place -> pay -> ship -> confirm -> review
#       "read"  = a read-side surface of the same milestone (admin order list /
#                 order detail with discountAmount). Read-side scripts must be
#                 pure reads, otherwise requirement (b) below cannot hold.
#
# ★ 顺序即执行顺序：读侧的两条放在链路段【之后】—— 它们断言的是「链路跑完之后
#   库里那些订单长什么样」，所以必须在链路产生数据之后再跑。
RUNS = [
    ("Day 14", "day14-e2e-walk.py", "day14-e2e-walk-report.txt",
     "place -> pay  (both state-machine exits + the ledger)", "chain"),
    ("Day 15", "day15-ship-confirm.py", "day15-ship-confirm-report.txt",
     "pay -> ship -> confirm", "chain"),
    ("Day 16", "day16-review-e2e.py", "day16-review-e2e-report.txt",
     "confirm -> review", "chain"),
    ("Day 17a", "day17-a-order-list-verify.py", "day17-a-order-list-verify-report.txt",
     "read-side: admin order list, 10 fields reconciled against the DB", "read"),
    ("Day 17b", "day17-b-order-detail-verify.py", "day17-b-order-detail-verify-report.txt",
     "read-side: order detail, 15 fields + items (the T2 blind spot)", "read"),
]

# ★ 护栏：名单长度写死。改名单却忘了同步报告段落/verdict 逻辑时，这里会立刻炸
#   （同 day20-coupon-verify.py 的 EXPECTED 常量 —— 那道护栏第一次跑就抓到过错）。
EXPECTED_RUNS = 5

assert len(RUNS) == EXPECTED_RUNS, (
    "RUNS has %d entries, EXPECTED_RUNS says %d -- update both (and the verdict "
    "section that counts them)" % (len(RUNS), EXPECTED_RUNS))

_lines = []


def say(s=""):
    _lines.append(s)


def flush():
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(_lines) + "\n")


# ---------------------------------------------------------------- db helpers
def psql(sql):
    """★ stderr must be surfaced: reading only stdout turns an SQL error into 'no data'."""
    p = subprocess.run(
        [DOCKER, "exec", "-i", "-e", "PGCLIENTENCODING=UTF8",
         "mallx-postgres", "psql", "-U", "mallx", "-d", "mallx",
         "-t", "-A", "-F", "|", "-c", sql],
        capture_output=True)
    out = p.stdout.decode("utf-8", "replace").strip()
    err = p.stderr.decode("utf-8", "replace").strip()
    if p.returncode != 0 or "ERROR" in err:
        raise RuntimeError("psql failed (rc=%d)\nSQL: %s\nstderr: %s"
                           % (p.returncode, sql, err))
    return out


def one(sql):
    """Single scalar. ⚠️ docker exec returns lines with a trailing \\r -- strip it."""
    return psql(sql).strip()


COUNTS = [
    ("orders", "SELECT count(*) FROM orders"),
    ("order_items", "SELECT count(*) FROM order_items"),
    ("payments", "SELECT count(*) FROM payments"),
    ("reviews", "SELECT count(*) FROM reviews"),
    ("inventory_logs", "SELECT count(*) FROM inventory_logs"),
    ("cart_items", "SELECT count(*) FROM cart_items"),
]

INVARIANTS = [
    ("stock identity: available + locked + sold == total",
     "SELECT count(*) FROM inventories "
     "WHERE available_stock + locked_stock + sold_stock <> total_stock"),
    ("no negative stock buckets",
     "SELECT count(*) FROM inventories "
     "WHERE available_stock < 0 OR locked_stock < 0 OR sold_stock < 0"),
    ("at most one review per order_item",
     "SELECT count(*) FROM (SELECT order_item_id FROM reviews "
     "GROUP BY order_item_id HAVING count(*) > 1) t"),
    ("no review on a non-COMPLETED order",
     "SELECT count(*) FROM reviews r "
     "JOIN order_items oi ON oi.id = r.order_item_id "
     "JOIN orders o ON o.id = oi.order_id WHERE o.status <> 'COMPLETED'"),
    ("every review belongs to a real order_item",
     "SELECT count(*) FROM reviews r "
     "LEFT JOIN order_items oi ON oi.id = r.order_item_id WHERE oi.id IS NULL"),
]

INV_SQL = ("SELECT sku_id||'|'||total_stock||'|'||available_stock||'|'"
           "||locked_stock||'|'||sold_stock FROM inventories ORDER BY sku_id")


def snapshot():
    return {"counts": {k: int(one(q)) for k, q in COUNTS},
            "inv": one(INV_SQL),
            "bad": {name: int(one(q)) for name, q in INVARIANTS}}


def show_inv(rows, indent="    "):
    for row in rows.splitlines():
        p = row.split("|")
        if len(p) == 5:
            say("%ssku %-3s total=%-5s available=%-5s locked=%-5s sold=%s"
                % (indent, p[0], p[1], p[2], p[3], p[4]))


# ---------------------------------------------------------------- report reader
def read_report(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def parse(path):
    """Pull the summary + the script's own section headers out of its report."""
    text = read_report(path)
    m = re.search(r"ASSERTIONS:\s*(\d+)\s*/\s*(\d+)\s*passed", text)
    if not m:
        m2 = re.search(r"RESULT:\s*(\d+)\s*/\s*(\d+)\s*passed", text)
        m = m2
    if not m:
        # ★★ Day 24（T2 落地时补）：day17-a / day17-b 用的是【另一套】报告结尾 ——
        #      "VERDICT: OK —— 26 / 26 项全过"
        #    它们的"断言总数"这一行与 day14/15/16 的 "ASSERTIONS: n / m passed" 不同。
        #    ★ 这里要修的是【collector】，不是那两个脚本 ——
        #      判据：「M1 是 collector，读各脚本【自己的】报告」，这是设计；
        #      两个脚本已各自验收通过，改它们的输出等于改已验证对象来迁就工具。
        #    （这与 Day 20 「脚本与设计打架时改脚本」不矛盾：那次是断言写错，
        #      这次是采集器读不出既有格式 —— 错在采集器的宽容度。）
        m = re.search(r"VERDICT:\s*\S+\s*[—\-]+\s*(\d+)\s*/\s*(\d+)", text)
    passed, total = (int(m.group(1)), int(m.group(2))) if m else (None, None)
    sections = [ln.strip() for ln in text.splitlines()
                if re.match(r"^\[\d+\]\s", ln.strip())]
    restored = [ln.strip() for ln in text.splitlines()
                if "back at baseline" in ln or "baseline" in ln.lower()
                and ("byte" in ln.lower() or "restore" in ln.lower())]
    return dict(passed=passed, total=total, sections=sections, restored=restored)


# ---------------------------------------------------------------- modes
def mode_baseline():
    say("=" * 78)
    say("MallX  M1 milestone regression   step 1/2 -- BASELINE")
    say("=" * 78)
    say("run at : %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    snap = snapshot()
    for k, v in snap["counts"].items():
        say("  %-16s = %d" % (k, v))
    say("  inventories:")
    show_inv(snap["inv"])
    say("  invariants (all must be 0):")
    ok = True
    for name, _ in INVARIANTS:
        v = snap["bad"][name]
        say("    %-42s = %d" % (name, v))
        ok = ok and v == 0
    say("")
    say("  baseline invariant-clean : %s" % ("YES" if ok else "NO -- see above"))
    with open(BASELINE, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)
    with open(STAMP, "w", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
    say("")
    say("  wrote %s" % os.path.basename(BASELINE))
    say("  wrote %s   <-- reports must be regenerated AFTER this instant"
        % os.path.basename(STAMP))
    say("")
    say("NEXT: run the three chain scripts one at a time, then re-run this script"
        " without --baseline.")
    say("=" * 78)
    flush()
    print("BASELINE captured")
    print("report -> %s" % OUT)
    return 0


def mode_collect():
    say("=" * 78)
    say("MallX  M1 milestone regression   (place -> pay -> ship -> confirm -> review)")
    say("=" * 78)
    say("run at : %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    say("")

    stamp_mtime = os.path.getmtime(STAMP) if os.path.exists(STAMP) else None
    baseline = None
    if os.path.exists(BASELINE):
        with open(BASELINE, encoding="utf-8") as f:
            baseline = json.load(f)

    # ------------------------------------------------------ [1] the reports
    # ★ 分两小节输出：链路段（生产数据的那条路）与读侧段（消费同一条数据）。
    #   把两者混在一张清单里，会让「链路绿了」这句话变得含糊 ——
    #   读者分不清「端到端走通」与「出参字段对得上」。
    say("[1] CHAIN -- each link's own end-to-end report, regenerated in this run")
    say("    (produce side: place -> pay -> ship -> confirm -> review)")
    results = []
    for day, script, report, link, kind in RUNS:
        if kind != "chain":
            continue
        path = os.path.join(HERE, report)
        say("  -> %s  %s" % (day, script))
        say("     proves: %s" % link)
        if not os.path.exists(path):
            say("     report MISSING: %s" % report)
            results.append(dict(day=day, script=script, link=link, kind=kind,
                                fresh=False, passed=None, total=None, when=None,
                                parsed=None, missing=True))
            say("")
            continue
        when = os.path.getmtime(path)
        fresh = (stamp_mtime is None) or (when > stamp_mtime)
        p = parse(path)
        results.append(dict(day=day, script=script, link=link, kind=kind, fresh=fresh,
                            passed=p["passed"], total=p["total"], when=when,
                            parsed=p, missing=False))
        say("     report mtime : %s   (%s)"
            % (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(when)),
               "regenerated this run" if fresh else "★ STALE -- older than the stamp"))
        if p["passed"] is None:
            say("     RESULT: 读不出断言数 —— 文件在，但没有 ASSERTIONS/RESULT/VERDICT 行")
        else:
            say("     RESULT: %d / %d passed" % (p["passed"], p["total"]))
        for ln in p["sections"]:
            say("       %s" % ln)
        say("")

    say("[1b] READ-SIDE -- the same milestone's read surfaces (T2)")
    say("     ★ these are the two scripts that were NOT on the list until Day 24 --")
    say("       which is exactly how Day 22's OrderDetailVO discountAmount drift")
    say("       slipped past every automated regression.")
    for day, script, report, link, kind in RUNS:
        if kind != "read":
            continue
        path = os.path.join(HERE, report)
        say("  -> %s  %s" % (day, script))
        say("     proves: %s" % link)
        if not os.path.exists(path):
            say("     report MISSING: %s" % report)
            results.append(dict(day=day, script=script, link=link, kind=kind,
                                fresh=False, passed=None, total=None, when=None,
                                parsed=None, missing=True))
            say("")
            continue
        when = os.path.getmtime(path)
        fresh = (stamp_mtime is None) or (when > stamp_mtime)
        p = parse(path)
        results.append(dict(day=day, script=script, link=link, kind=kind, fresh=fresh,
                            passed=p["passed"], total=p["total"], when=when,
                            parsed=p, missing=False))
        say("     report mtime : %s   (%s)"
            % (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(when)),
               "regenerated this run" if fresh else "★ STALE -- older than the stamp"))
        if p["passed"] is None:
            say("     RESULT: 读不出断言数 —— 文件在，但没有 ASSERTIONS/RESULT/VERDICT 行")
        else:
            say("     RESULT: %d / %d passed" % (p["passed"], p["total"]))
        say("")

    # ★ 护栏：报告条数必须与名单一致 —— 漏跑一条时「少了」这件事本身要现形，
    #   而不是让 verdict 在一份短名单上「全绿」。
    say("[1c] COVERAGE")
    say("     listed %d, collected %d   %s"
        % (EXPECTED_RUNS, len(results),
           "OK" if len(results) == EXPECTED_RUNS else "★ MISMATCH -- a script was not run"))
    say("")

    # ------------------------------------------------------ [2] the database
    say("[2] DATABASE -- snapshot now, compare with the baseline")
    after = snapshot()
    if baseline is None:
        say("  ★ no baseline file -- cannot assert 'restored'. Re-run with --baseline first.")
        clean = None
    else:
        clean = True
        for k in baseline["counts"]:
            b, a = baseline["counts"][k], after["counts"][k]
            same = (a == b)
            clean = clean and same
            say("  %-16s = %-5d %s" % (k, a, "unchanged" if same else
                                       "★ CHANGED from %d" % b))
        inv_same = (baseline["inv"] == after["inv"])
        clean = clean and inv_same
        say("  inventories     : %s" % ("identical to baseline" if inv_same
                                        else "★ DIFFERS from baseline"))
        show_inv(after["inv"], indent="      ")
        if not inv_same:
            say("    baseline was:")
            show_inv(baseline["inv"], indent="      ")
    say("  milestone invariants (all must be 0):")
    all_zero = True
    for name, _ in INVARIANTS:
        v = after["bad"][name]
        say("    %-42s = %d" % (name, v))
        all_zero = all_zero and v == 0
    say("")

    # ------------------------------------------------------ [3] verdict
    say("=" * 78)
    say("MILESTONE M1  --  verdict")
    say("=" * 78)
    chain = [r for r in results if r["kind"] == "chain"]
    read = [r for r in results if r["kind"] == "read"]

    def green(rs):
        return all(r["passed"] is not None and r["passed"] == r["total"] and r["fresh"]
                   for r in rs)

    chain_green = green(chain)
    read_green = green(read)
    coverage_ok = (len(results) == EXPECTED_RUNS)

    for r in results:
        tag = "chain" if r["kind"] == "chain" else "read "
        if r["passed"] is None:
            # ★ 区分两种「读不出来」—— 它们的排查方向完全不同：
            #   文件不存在 ⇒ 那个脚本根本没跑；
            #   文件在但无断言行 ⇒ 报告格式变了 / 正则没覆盖（本次 T2 落地时就撞上过：
            #   day17-a/b 用的是「VERDICT: OK —— 26 / 26 项全过」，与 day14/15/16 不同）。
            #   合并成一句 "NO REPORT" 会把后者误导成前者。
            #   （同 Day 20 那个被误读的 "VERDICT: false"：**输出必须自带判别信息**。）
            why = ("NO REPORT FILE -- 该脚本没跑" if r.get("missing")
                   else "UNPARSED -- 文件在，但没有可识别的断言行")
            say("  [%s] %-8s %-32s %s" % (tag, r["day"], r["script"], why))
        else:
            ok = (r["passed"] == r["total"]) and r["fresh"]
            say("  [%s] %-8s %-32s %d/%d  %s   (%s)"
                % (tag, r["day"], r["script"], r["passed"], r["total"],
                   "PASS" if ok else "FAIL",
                   "this run" if r["fresh"] else "STALE report"))
    say("")
    say("  (a) every CHAIN link all-green        : %s" % ("YES" if chain_green else "NO"))
    say("  (a2) every READ-SIDE check all-green  : %s" % ("YES" if read_green else "NO"))
    say("  (b) all %d listed reports collected    : %s"
        % (EXPECTED_RUNS, "YES" if coverage_ok else "NO -- see [1c]"))
    say("  (c) database back at baseline         : %s"
        % ("YES" if clean else ("UNKNOWN (no baseline)" if clean is None else "NO")))
    say("  (d) milestone invariants all zero     : %s" % ("YES" if all_zero else "NO"))
    verdict = chain_green and read_green and coverage_ok and (clean is True) and all_zero
    say("")
    say("  M1 REGRESSION: %s" % ("OK -- the chain still works, the read surfaces still"
                                " match, and the books balance"
                                if verdict else "NOT CLEAN -- see FAIL/STALE/DIFFERS above"))
    say("=" * 78)
    flush()

    tp = sum(r["passed"] or 0 for r in results)
    tt = sum(r["total"] or 0 for r in results)
    print("ASSERTIONS ACROSS M1 (%d scripts): %d / %d passed" % (len(results), tp, tt))
    print("CHAIN ALL-GREEN: %s   READ-SIDE ALL-GREEN: %s   COVERAGE: %d/%d"
          % ("YES" if chain_green else "NO", "YES" if read_green else "NO",
             len(results), EXPECTED_RUNS))
    print("BASELINE RESTORED: %s" % ("YES" if clean else ("UNKNOWN" if clean is None else "NO")))
    print("M1 REGRESSION: %s" % ("OK" if verdict else "NOT CLEAN"))
    print("report -> %s" % OUT)
    return 0 if verdict else 1


if __name__ == "__main__":
    try:
        if "--baseline" in sys.argv:
            sys.exit(mode_baseline())
        sys.exit(mode_collect())
    except Exception:                                                  # noqa: BLE001
        import traceback
        say("\nCRASH:\n" + traceback.format_exc())
        flush()
        raise
