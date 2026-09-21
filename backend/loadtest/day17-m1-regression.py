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
    2)  run day14-e2e-walk.py, day15-ship-confirm.py, day16-review-e2e.py
        (one at a time, from the shell)
    3)  python day17-m1-regression.py                 # collect + compare + verdict

Step 1 writes day17-m1-baseline.json and day17-m1-stamp.txt; step 3 uses the stamp
to prove each report was regenerated AFTER the stamp (i.e. by this run, not a stale
file from last week).

Repeatable: yes. The three chain scripts are self-cleaning, so this whole sequence
can be run any time and leaves the database where it found it.
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

# link -> (script, report)
RUNS = [
    ("Day 14", "day14-e2e-walk.py", "day14-e2e-walk-report.txt",
     "place -> pay  (both state-machine exits + the ledger)"),
    ("Day 15", "day15-ship-confirm.py", "day15-ship-confirm-report.txt",
     "pay -> ship -> confirm"),
    ("Day 16", "day16-review-e2e.py", "day16-review-e2e-report.txt",
     "confirm -> review"),
]
DAY14, DAY15 = RUNS[1][0], RUNS[2][0]

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

    # ------------------------------------------------------ [1] the three links
    say("[1] CHAIN -- each link's own end-to-end report, regenerated in this run")
    results = []
    for day, script, report, link in RUNS:
        path = os.path.join(HERE, report)
        say("  -> %s  %s" % (day, script))
        say("     proves: %s" % link)
        if not os.path.exists(path):
            say("     report MISSING: %s" % report)
            results.append(dict(day=day, script=script, link=link, fresh=False,
                                passed=None, total=None, when=None, parsed=None))
            say("")
            continue
        when = os.path.getmtime(path)
        fresh = (stamp_mtime is None) or (when > stamp_mtime)
        p = parse(path)
        results.append(dict(day=day, script=script, link=link, fresh=fresh,
                            passed=p["passed"], total=p["total"], when=when,
                            parsed=p))
        say("     report mtime : %s   (%s)"
            % (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(when)),
               "regenerated this run" if fresh else "★ STALE -- older than the stamp"))
        if p["passed"] is None:
            say("     RESULT: no ASSERTIONS line found")
        else:
            say("     RESULT: %d / %d passed" % (p["passed"], p["total"]))
        for ln in p["sections"]:
            say("       %s" % ln)
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
    all_green = all(r["passed"] is not None and r["passed"] == r["total"] and r["fresh"]
                    for r in results)
    for r in results:
        if r["passed"] is None:
            say("  %-8s %-24s NO REPORT" % (r["day"], r["script"]))
        else:
            ok = (r["passed"] == r["total"]) and r["fresh"]
            say("  %-8s %-24s %d/%d  %s   (%s)"
                % (r["day"], r["script"], r["passed"], r["total"],
                   "PASS" if ok else "FAIL",
                   "this run" if r["fresh"] else "STALE report"))
    say("")
    say("  (a) every link all-green              : %s" % ("YES" if all_green else "NO"))
    say("  (b) database back at baseline         : %s"
        % ("YES" if clean else ("UNKNOWN (no baseline)" if clean is None else "NO")))
    say("  (c) milestone invariants all zero     : %s" % ("YES" if all_zero else "NO"))
    verdict = all_green and (clean is True) and all_zero
    say("")
    say("  M1 REGRESSION: %s" % ("OK -- the chain still works and the books balance"
                                if verdict else "NOT CLEAN -- see FAIL/STALE/DIFFERS above"))
    say("=" * 78)
    flush()

    tp = sum(r["passed"] or 0 for r in results)
    tt = sum(r["total"] or 0 for r in results)
    print("ASSERTIONS ACROSS CHAIN: %d / %d passed" % (tp, tt))
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
