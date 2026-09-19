# -*- coding: utf-8 -*-
"""
Day 14 Step 5 -- END-TO-END WALK: both exit edges of the order state machine,
in one script, against the live app, ending back at the §0.3 baseline.

Why this script exists
----------------------
Steps 1-4 each proved one thing in isolation:
    Step 1  cancel works                          (34/34)
    Step 2  cancel vs pay race on the status bit  (16/16 + 11/11 control)
    Step 3  the timeout sweeper closes orders     (22/22)
    Step 4  the ledger records all three moves    (61/61)
    Step 5  the ledger audits the whole DB        (28/28)

But the Day 14 doc §七 item 1 asked for something none of them did: walk the
SAME starting state down BOTH exits, one after the other, and confirm the books
balance after each. Step 4 exercised place->pay and place->cancel->release as
separate legs; this script makes the two paths a single deliberate A/B.

The state machine, and where the two paths diverge
--------------------------------------------------
                    place order
                        |
                        v
                 PENDING_PAYMENT  --------------------+
                   |        |                         |
             cancel|        |pay                 (locked +1)
                   v        v
              CANCELLED    PAID
                   |        |
        available +n|        |available UNCHANGED
         locked  -n|        |locked -n / sold +n
                   v        v
        goods return to shelf      goods leave for good

Both paths start from the same tuple and take the same first step (locked +1,
available -1). They diverge ONLY at the exit edge. That divergence is the whole
point of Day 14, so it deserves a direct A/B on one unchanged baseline.

What is asserted (in order of importance)
-----------------------------------------
  * ★★ The two paths are IDENTICAL up to PENDING_PAYMENT: same delta, same
    ledger row type (ORDER_LOCK), same change (-1). The exit edge is the only
    difference -- which is exactly what a state machine means.
  * ★★ Cancel returns the unit to available; pay does NOT touch available.
    Both end with locked back to 0, but available differs by exactly 1.
  * ★ The ledger explains the present after BOTH paths: available_now == A0 + Σ(change).
  * ★ Business conservation holds at the end: locked == Σ(PENDING_PAYMENT units) == 0.
  * ★★ CLEANUP IS EXACT: after deleting this run's artifacts, all 7 SKUs are
    byte-for-byte equal to the baseline captured at start, and the ledger is empty.
    So the script is RE-RUNNABLE and leaves no trace.

★ Ordering note: cleanup runs in a `finally`, so a failed assertion still leaves
  the database at baseline (evidence survives in the report, not in the tables).

Usage:
    python day14-e2e-walk.py
Report (utf-8) is written next to this file: day14-e2e-walk-report.txt
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080"
DOCKER = r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
TARGET_SKU = 4          # MATE80-BLK-512 @ 6999.00
ADDRESS_ID = 2          # demo's default address
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "day14-e2e-walk-report.txt")

_lines = []


def say(s=""):
    _lines.append(s)


def flush():
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(_lines) + "\n")


# ---------------------------------------------------------------- http helper
def api(method, path, token=None, body=None, timeout=60):
    """Return (http_status, raw_text). Proxy explicitly disabled.

    ★ 必须禁代理：会话注入了 HTTP_PROXY，system 代理会把 127.0.0.1 也拦下，
      报 `502 upstream connect failed` —— 看起来像服务挂了。
    """
    headers = {}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:                                            # noqa: BLE001
        return -1, '{"transport_error": "%s"}' % repr(e)


def japi(method, path, token=None, body=None):
    st, raw = api(method, path, token, body)
    try:
        return st, json.loads(raw), raw
    except ValueError:
        return st, {"raw": raw}, raw


# ---------------------------------------------------------------- db helpers
def psql(sql):
    """★ 必须把 stderr 暴露出来：只读 stdout 时，SQL 错误会伪装成「没数据」。
    （Day 14 第 5 步踩过这个坑：AUDIT_SQL 漏了分号，报错被吞成空结果。）"""
    p = subprocess.run(
        [DOCKER, "exec", "-i", "-e", "PGCLIENTENCODING=UTF8",
         "mallx-postgres", "psql", "-U", "mallx", "-d", "mallx",
         "-t", "-A", "-F", "|", "-c", sql],
        capture_output=True)
    out = p.stdout.decode("utf-8", "replace").strip()
    err = p.stderr.decode("utf-8", "replace").strip()
    if p.returncode != 0 or "ERROR" in err:
        raise RuntimeError("psql failed (rc=%d)\nSQL: %s\nstderr: %s" % (p.returncode, sql, err))
    return out


def one(sql):
    """Single scalar. ⚠️ docker exec 回传的行尾带 \\r —— 不 strip 比对照样为假。"""
    return psql(sql).strip()


def all_inv():
    """Every SKU as a dict, keyed by sku_id. This is the baseline fingerprint."""
    out = one("SELECT sku_id||'|'||total_stock||'|'||available_stock||'|'"
              "||locked_stock||'|'||sold_stock"
              " FROM inventories ORDER BY sku_id")
    rows = {}
    for line in out.splitlines():
        p = [x.strip() for x in line.split("|")]
        if len(p) == 5:
            rows[int(p[0])] = dict(total=int(p[1]), available=int(p[2]),
                                   locked=int(p[3]), sold=int(p[4]))
    return rows


def inv(sku):
    return all_inv()[sku]


def inv_line(tag, sku, r):
    return "  %-20s sku%d  total=%3d  available=%3d  locked=%3d  sold=%3d  identity=%s" % (
        tag, sku, r["total"], r["available"], r["locked"], r["sold"],
        "OK" if r["total"] == r["available"] + r["locked"] + r["sold"] else "BROKEN")


def delta(a, b):
    return "available %+d  locked %+d  sold %+d" % (
        b["available"] - a["available"], b["locked"] - a["locked"], b["sold"] - a["sold"])


def ledger(sku, after_id=0):
    out = one("SELECT id||'|'||type||'|'||change_quantity||'|'||before_stock||'|'"
              "||after_stock||'|'||coalesce(reference_id::text,'NULL')||'|'"
              "||to_char(created_at,'HH24:MI:SS.MS')"
              " FROM inventory_logs WHERE sku_id=%d AND id>%d ORDER BY id" % (sku, after_id))
    rows = []
    for line in out.splitlines():
        p = [x.strip() for x in line.split("|")]
        if len(p) == 7:
            rows.append(dict(id=int(p[0]), type=p[1], change=int(p[2]), before=int(p[3]),
                             after=int(p[4]), ref=p[5], at=p[6]))
    return rows


def ledger_count():
    return int(one("SELECT count(*) FROM inventory_logs"))


def order_status(order_id):
    return one("SELECT status FROM orders WHERE id=%d" % order_id) or "(missing)"


def short(raw, n=160):
    raw = raw.replace("\r", "").replace("\n", " ").strip()
    return raw if len(raw) <= n else raw[:n] + " ...(truncated)"


def dump(tag, rows):
    if tag:
        say("  %s" % tag)
    say("    %-4s %-16s %8s %8s %8s %-8s %s"
        % ("id", "type", "change", "before", "after", "ref", "at"))
    for r in rows:
        say("    %-4d %-16s %+8d %8d %8d %-8s %s"
            % (r["id"], r["type"], r["change"], r["before"], r["after"], r["ref"], r["at"]))


class _Abort(Exception):
    """Early abort that still runs the cleanup in `finally` and still writes the
    report. (A bare `return` would skip the summary + flush.)"""


# ================================================================ main
def main():
    checks = []

    def chk(name, good):
        checks.append((name, bool(good)))

    say("=" * 78)
    say("Day 14 Step 5 -- END-TO-END WALK: both exit edges, one unchanged baseline")
    say("target : %s   account: demo(id=1)   sku under test: %d" % (BASE, TARGET_SKU))
    say("=" * 78)

    # ---------------------------------------------------------- [0] baseline
    say("\n[0] BASELINE FINGERPRINT (all 7 SKUs)")
    base_all = all_inv()
    base = base_all[TARGET_SKU]
    A0 = base["available"]
    high_water = int(one("SELECT coalesce(max(id),0) FROM inventory_logs"))
    base_counts = one("SELECT (SELECT count(*) FROM orders)||'/'||"
                      "(SELECT count(*) FROM payments)||'/'||"
                      "(SELECT count(*) FROM order_items)||'/'||"
                      "(SELECT count(*) FROM inventory_logs)")
    for sku in sorted(base_all):
        say(inv_line("baseline", sku, base_all[sku]))
    say("  rows orders/payments/order_items/inventory_logs = %s" % base_counts)
    say("  ★ A0 = available_stock of sku%d at start = %d" % (TARGET_SKU, A0))
    say("  ★ ledger high-water id = %d (only rows id > %d are judged)" % (high_water, high_water))
    chk("every SKU satisfies total = available + locked + sold",
        all(r["total"] == r["available"] + r["locked"] + r["sold"] for r in base_all.values()))
    chk("baseline ledger is empty", high_water == 0)
    chk("baseline has no PENDING_PAYMENT order (locked must be 0 everywhere)",
        one("SELECT count(*) FROM orders WHERE status='PENDING_PAYMENT'").strip() == "0")

    # ---------------------------------------------------------- [1] login
    say("\n[1] login demo (token stays in memory, never on disk)")
    st, b, _ = japi("POST", "/api/auth/login", body={"username": "demo", "password": "demo123"})
    demo = (b.get("data") or {}).get("token")
    say("  demo http=%s code=%s userId=%s token_len=%d" % (
        st, b.get("code"), (b.get("data") or {}).get("userId"), len(demo or "")))
    chk("login succeeded", bool(demo))
    if not demo:
        say("\nABORT: no token")
        flush()
        return 1

    # ---------------------------------------------------------------- helpers
    def cart_all():
        st_, b_, _ = japi("GET", "/api/cart", token=demo)
        return (b_.get("data") or {}).get("items") or []

    def cart_find(sku):
        for it in cart_all():
            if it.get("skuId") == sku:
                return it
        return None

    def select_only(item_id):
        """★ Deselect everything else first -- createFromCart consumes ALL selected
        lines, so a leftover selection would silently join the order."""
        for it in cart_all():
            want = (it["id"] == item_id)
            if bool(it.get("selected")) != want:
                japi("PUT", "/api/cart/%s/selected" % it["id"], token=demo,
                     body={"selected": want})

    def place_order(sku=TARGET_SKU, qty=1):
        it = cart_find(sku)
        if it is None:
            japi("POST", "/api/cart", token=demo, body={"skuId": sku, "quantity": qty})
            it = cart_find(sku)
        if it is None:
            return None, None, None
        japi("PUT", "/api/cart/%s" % it["id"], token=demo, body={"quantity": qty})
        select_only(it["id"])
        st_, b_, raw_ = japi("POST", "/api/orders", token=demo, body={"addressId": ADDRESS_ID})
        oid = b_.get("data") if st_ == 200 and isinstance(b_.get("data"), int) else None
        return oid, b_.get("code"), raw_

    def pay(order_id, method="ALIPAY"):
        st_, b_, _ = japi("POST", "/api/payments", token=demo,
                          body={"orderId": order_id, "method": method})
        return st_, b_

    def cancel(order_id):
        st_, b_, raw_ = japi("POST", "/api/orders/%d/cancel" % order_id, token=demo)
        return st_, b_, raw_

    created = []            # order ids this run created -> cleanup targets

    try:
        # ================================================== PATH A: cancel
        say("\n" + "-" * 78)
        say("PATH A -- place, then CANCEL (goods return to the shelf)")
        say("-" * 78)

        say("\n[2] PATH A / place order A (sku%d x1)" % TARGET_SKU)
        order_a, code_a, raw_a = place_order()
        say("  POST /api/orders -> order=%s code=%s %s" % (order_a, code_a, short(raw_a, 90)))
        chk("PATH A: order A created", isinstance(order_a, int))
        if not isinstance(order_a, int):
            say("\nABORT: could not create order A")
            raise _Abort()
        created.append(order_a)
        say("  order A status = %s" % order_status(order_a))
        chk("PATH A: order A is PENDING_PAYMENT", order_status(order_a) == "PENDING_PAYMENT")
        a1 = inv(TARGET_SKU)
        say(inv_line("after place A", TARGET_SKU, a1))
        say("  delta vs start: %s" % delta(base, a1))
        chk("PATH A: placing moved available -1 / locked +1 / sold +0",
            a1["available"] == A0 - 1 and a1["locked"] == base["locked"] + 1
            and a1["sold"] == base["sold"])

        rows_a = ledger(TARGET_SKU, high_water)
        chk("PATH A: exactly one ledger row after place", len(rows_a) == 1)
        if rows_a:
            r = rows_a[0]
            chk("PATH A: row is ORDER_LOCK", r["type"] == "ORDER_LOCK")
            chk("PATH A: ORDER_LOCK change is -1", r["change"] == -1)
            chk("PATH A: ORDER_LOCK before == A0", r["before"] == A0)
            chk("PATH A: ORDER_LOCK reference_id is NULL (order not inserted yet)",
                r["ref"] == "NULL")

        say("\n[3] PATH A / cancel order A")
        st_c, b_c, raw_c = cancel(order_a)
        say("  POST /api/orders/%d/cancel -> http=%s code=%s" % (order_a, st_c, b_c.get("code")))
        chk("PATH A: cancel succeeded", st_c == 200 and b_c.get("code") == 200)
        say("  order A status now = %s" % order_status(order_a))
        chk("PATH A: order A is CANCELLED", order_status(order_a) == "CANCELLED")
        a2 = inv(TARGET_SKU)
        say(inv_line("after cancel A", TARGET_SKU, a2))
        say("  delta vs after-place: %s" % delta(a1, a2))
        chk("PATH A: cancelling moved available +1 / locked -1 / sold +0",
            a2["available"] == a1["available"] + 1 and a2["locked"] == a1["locked"] - 1
            and a2["sold"] == a1["sold"])

        rows_a = ledger(TARGET_SKU, high_water)
        chk("PATH A: ledger now has 2 rows", len(rows_a) == 2)
        if len(rows_a) >= 2:
            r = rows_a[1]
            chk("PATH A: second row is CANCEL_RELEASE", r["type"] == "CANCEL_RELEASE")
            chk("PATH A: CANCEL_RELEASE change is +1", r["change"] == 1)
            chk("PATH A: CANCEL_RELEASE reference_id == order A", r["ref"] == str(order_a))

        say("\n[3b] PATH A / reconcile -- the shelf is exactly where it started")
        sum_a = sum(r["change"] for r in rows_a)
        say("  A0 = %d   Σ(change) = %+d   A0 + Σ = %d   available now = %d"
            % (A0, sum_a, A0 + sum_a, a2["available"]))
        chk("★★ PATH A: ledger sum reproduces available_stock", A0 + sum_a == a2["available"])
        chk("★★ PATH A: available returned to A0 exactly", a2["available"] == A0)
        chk("PATH A: locked returned to 0", a2["locked"] == 0)
        chk("PATH A: sold untouched by the whole path", a2["sold"] == base["sold"])
        chk("PATH A: total is conserved", a2["total"] == base["total"])

        # ================================================== PATH B: pay
        say("\n" + "-" * 78)
        say("PATH B -- place, then PAY (goods leave for good)")
        say("-" * 78)

        say("\n[4] PATH B / place order B (sku%d x1)" % TARGET_SKU)
        order_b, code_b, raw_b = place_order()
        say("  POST /api/orders -> order=%s code=%s %s" % (order_b, code_b, short(raw_b, 90)))
        chk("PATH B: order B created", isinstance(order_b, int))
        if not isinstance(order_b, int):
            say("\nABORT: could not create order B")
            raise _Abort()
        created.append(order_b)
        say("  order B status = %s" % order_status(order_b))
        chk("PATH B: order B is PENDING_PAYMENT", order_status(order_b) == "PENDING_PAYMENT")
        b1 = inv(TARGET_SKU)
        say(inv_line("after place B", TARGET_SKU, b1))
        say("  delta vs start: %s" % delta(base, b1))
        chk("PATH B: placing moved available -1 / locked +1 / sold +0",
            b1["available"] == A0 - 1 and b1["locked"] == base["locked"] + 1
            and b1["sold"] == base["sold"])

        rows_b = ledger(TARGET_SKU, high_water)
        chk("PATH B: ledger has 3 rows now", len(rows_b) == 3)
        if len(rows_b) >= 3:
            r = rows_b[2]
            chk("PATH B: third row is ORDER_LOCK", r["type"] == "ORDER_LOCK")
            chk("PATH B: ORDER_LOCK change is -1", r["change"] == -1)
            chk("PATH B: ORDER_LOCK reference_id is NULL", r["ref"] == "NULL")

        say("\n[5] PATH B / pay order B")
        st_p, b_p = pay(order_b)
        pd = b_p.get("data") or {}
        say("  POST /api/payments -> http=%s code=%s paymentId=%s"
            % (st_p, b_p.get("code"), pd.get("id")))
        chk("PATH B: payment succeeded", st_p == 200 and b_p.get("code") == 200)
        say("  order B status now = %s" % order_status(order_b))
        chk("PATH B: order B is PAID", order_status(order_b) == "PAID")
        b2 = inv(TARGET_SKU)
        say(inv_line("after pay B", TARGET_SKU, b2))
        say("  delta vs after-place: %s   ★ available must NOT move" % delta(b1, b2))
        chk("PATH B: paying left available_stock untouched", b2["available"] == b1["available"])
        chk("PATH B: paying moved locked -1 / sold +1",
            b2["locked"] == b1["locked"] - 1 and b2["sold"] == b1["sold"] + 1)

        rows_b = ledger(TARGET_SKU, high_water)
        chk("PATH B: ledger has 4 rows now", len(rows_b) == 4)
        if len(rows_b) >= 4:
            r = rows_b[3]
            chk("PATH B: fourth row is PAY_SOLD", r["type"] == "PAY_SOLD")
            chk("★★ PATH B: PAY_SOLD change == 0 (available must not move)", r["change"] == 0)
            chk("PATH B: PAY_SOLD before == after", r["before"] == r["after"])
            chk("PATH B: PAY_SOLD reference_id == order B", r["ref"] == str(order_b))

        say("\n[5b] PATH B / reconcile -- the shelf lost exactly one, and it is sold")
        sum_b = sum(r["change"] for r in rows_b)
        say("  A0 = %d   Σ(change) = %+d   A0 + Σ = %d   available now = %d"
            % (A0, sum_b, A0 + sum_b, b2["available"]))
        chk("★★ PATH B: ledger sum reproduces available_stock", A0 + sum_b == b2["available"])
        chk("★★ PATH B: available == A0 - 1", b2["available"] == A0 - 1)
        chk("PATH B: locked returned to 0", b2["locked"] == 0)
        chk("PATH B: sold is base + 1", b2["sold"] == base["sold"] + 1)
        chk("PATH B: total is conserved", b2["total"] == base["total"])

        # ================================================== [6] THE CONTRAST
        say("\n" + "=" * 78)
        say("[6] ★★ THE CONTRAST -- same start, same first step, different exit")
        say("=" * 78)
        say("  %-14s %10s %10s %8s %8s" % ("step", "available", "locked", "sold", "order status"))
        say("  %-14s %10d %10d %8d %s"
            % ("start", base["available"], base["locked"], base["sold"], "-"))
        say("  %-14s %10d %10d %8d %s"
            % ("A/placed", a1["available"], a1["locked"], a1["sold"], "PENDING_PAYMENT"))
        say("  %-14s %10d %10d %8d %s"
            % ("A/cancelled", a2["available"], a2["locked"], a2["sold"], "CANCELLED"))
        say("  %-14s %10d %10d %8d %s"
            % ("B/placed", b1["available"], b1["locked"], b1["sold"], "PENDING_PAYMENT"))
        say("  %-14s %10d %10d %8d %s"
            % ("B/paid", b2["available"], b2["locked"], b2["sold"], "PAID"))

        chk("★★ both paths are IDENTICAL up to PENDING_PAYMENT (same available/locked/sold)",
            (a1["available"], a1["locked"], a1["sold"])
            == (b1["available"], b1["locked"], b1["sold"]))
        chk("★ the two exits land on different available values",
            a2["available"] != b2["available"])
        chk("★ cancel ends A0; pay ends A0 - 1 (divergence is exactly 1 unit)",
            a2["available"] == A0 and b2["available"] == A0 - 1)
        chk("★ both exits leave locked at 0 (the lock is always resolved)",
            a2["locked"] == 0 and b2["locked"] == 0)
        chk("★ only the pay path increases sold", a2["sold"] == base["sold"]
            and b2["sold"] == base["sold"] + 1)

        # ================================================== [7] ledger audit
        say("\n" + "=" * 78)
        say("[7] LEDGER AUDIT OVER BOTH PATHS (4 rows, one contiguous chain)")
        say("=" * 78)
        rows = ledger(TARGET_SKU, high_water)
        dump("", rows)
        chk("4 ledger rows total", len(rows) == 4)
        chk("types are LOCK, RELEASE, LOCK, SOLD in order",
            [r["type"] for r in rows] == ["ORDER_LOCK", "CANCEL_RELEASE",
                                          "ORDER_LOCK", "PAY_SOLD"])
        chk("every row satisfies change == after - before",
            all(r["change"] == r["after"] - r["before"] for r in rows))
        breaks = [(rows[i - 1]["id"], rows[i - 1]["after"], rows[i]["id"], rows[i]["before"])
                  for i in range(1, len(rows)) if rows[i]["before"] != rows[i - 1]["after"]]
        for prev_id, prev_after, cur_id, cur_before in breaks:
            say("  BREAK between #%d (after=%d) and #%d (before=%d)"
                % (prev_id, prev_after, cur_id, cur_before))
        chk("★ no gaps in the chain", not breaks)
        chk("chain starts at A0", bool(rows) and rows[0]["before"] == A0)
        chk("chain ends at current available",
            bool(rows) and rows[-1]["after"] == b2["available"])
        total_change = sum(r["change"] for r in rows)
        say("  A0 = %d   Σ(change) = %+d   A0 + Σ = %d   available now = %d"
            % (A0, total_change, A0 + total_change, b2["available"]))
        chk("★★ A0 + Σ(change) == available_stock after BOTH paths",
            A0 + total_change == b2["available"])
        chk("★★ Σ(PAY_SOLD change) == 0 (payment never moves available)",
            sum(r["change"] for r in rows if r["type"] == "PAY_SOLD") == 0)

        # ================================================== [8] conservation
        say("\n[8] BUSINESS CONSERVATION (locked == Σ PENDING_PAYMENT units)")
        drift_locked = one("""
            WITH l AS (SELECT sku_id, locked_stock FROM inventories WHERE locked_stock <> 0),
                 p AS (SELECT oi.sku_id, SUM(oi.quantity) q FROM order_items oi
                         JOIN orders o ON o.id = oi.order_id
                        WHERE o.status='PENDING_PAYMENT' GROUP BY oi.sku_id)
            SELECT count(*) FROM l FULL OUTER JOIN p ON l.sku_id = p.sku_id
             WHERE COALESCE(l.locked_stock,0) <> COALESCE(p.q,0)
        """).strip()
        # ★ sold 口径：Day 15 起是 {PAID, SHIPPED, COMPLETED}，不再是 PAID 一个。
        #   发货/收货都不动 sold，但会把订单挪出 PAID —— 只认 PAID 会报【假漂移】。
        #   详见 docs/daily/Day-15-发货与确认收货.md §0.2。
        drift_sold = one("""
            WITH s AS (SELECT sku_id, sold_stock FROM inventories WHERE sold_stock <> 0),
                 p AS (SELECT oi.sku_id, SUM(oi.quantity) q FROM order_items oi
                         JOIN orders o ON o.id = oi.order_id
                        WHERE o.status IN ('PAID','SHIPPED','COMPLETED') GROUP BY oi.sku_id)
            SELECT count(*) FROM s FULL OUTER JOIN p ON s.sku_id = p.sku_id
             WHERE COALESCE(s.sold_stock,0) <> COALESCE(p.q,0)
        """).strip()
        say("  drifting SKUs -- locked: %s   sold: %s" % (drift_locked, drift_sold))
        chk("no negative stock anywhere",
            one("SELECT count(*) FROM inventories WHERE available_stock < 0"
                " OR locked_stock < 0 OR sold_stock < 0").strip() == "0")
        chk("★ business conservation holds (locked) -- 0 drifting SKUs", drift_locked == "0")

    except _Abort:
        say("\n(aborted early -- cleanup below still runs)")

    finally:
        # ================================================== [9] cleanup
        say("\n" + "=" * 78)
        say("[9] CLEANUP -- remove this run's artifacts, restore the baseline")
        say("=" * 78)
        say("  orders to delete: %s" % (created or "(none)"))
        say("  ledger rows to delete: id > %d" % high_water)
        say("  sku%d restored to: locked=%d sold=%d available=total-%d-%d"
            % (TARGET_SKU, base["locked"], base["sold"], base["sold"], base["locked"]))
        try:
            if created:
                ids = ",".join(str(o) for o in created)
                psql("DELETE FROM payments WHERE order_id IN (%s);"
                     " DELETE FROM order_items WHERE order_id IN (%s);"
                     " DELETE FROM orders WHERE id IN (%s);"
                     % (ids, ids, ids))
            psql("DELETE FROM inventory_logs WHERE id > %d;" % high_water)
            psql("UPDATE inventories SET locked_stock = %d, sold_stock = %d,"
                 " available_stock = total_stock - %d - %d,"
                 " updated_at = CURRENT_TIMESTAMP WHERE sku_id = %d;"
                 % (base["locked"], base["sold"], base["sold"], base["locked"], TARGET_SKU))
            chk("cleanup ran without SQL error", True)
        except Exception as e:                                        # noqa: BLE001
            say("  CLEANUP FAILED: %s" % e)
            chk("cleanup ran without SQL error", False)

        # -------------------------------------------------- [10] verify baseline
        say("\n[10] VERIFY -- the database is byte-for-byte back at baseline")
        after_all = all_inv()
        for sku in sorted(after_all):
            tag = "restored" if after_all[sku] == base_all.get(sku) else "DRIFTED"
            say(inv_line(tag, sku, after_all[sku]))
        mismatches = [sku for sku in base_all
                      if after_all.get(sku) != base_all[sku]]
        if mismatches:
            say("  MISMATCHED SKUs: %s" % mismatches)
        after_counts = one("SELECT (SELECT count(*) FROM orders)||'/'||"
                           "(SELECT count(*) FROM payments)||'/'||"
                           "(SELECT count(*) FROM order_items)||'/'||"
                           "(SELECT count(*) FROM inventory_logs)")
        say("  rows orders/payments/order_items/inventory_logs = %s   (baseline %s)"
            % (after_counts, base_counts))
        chk("★★ all 7 SKUs identical to the baseline fingerprint", not mismatches)
        chk("★ row counts identical to baseline", after_counts == base_counts)
        chk("ledger is empty again", ledger_count() == 0)
        chk("no orphan order_items left", one(
            "SELECT count(*) FROM order_items oi LEFT JOIN orders o ON o.id = oi.order_id"
            " WHERE o.id IS NULL").strip() == "0")
        chk("no orphan payments left", one(
            "SELECT count(*) FROM payments p LEFT JOIN orders o ON o.id = p.order_id"
            " WHERE o.id IS NULL").strip() == "0")
        chk("no PENDING_PAYMENT order left behind",
            one("SELECT count(*) FROM orders WHERE status='PENDING_PAYMENT'").strip() == "0")

    # ---------------------------------------------------------------- summary
    passed = sum(1 for _, ok in checks if ok)
    total = len(checks)
    say("\n" + "=" * 78)
    say("ASSERTIONS: %d / %d passed" % (passed, total))
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
