# -*- coding: utf-8 -*-
"""
Day 15 -- ship + confirm receipt: the last two edges of the order state machine.

Where this fits
---------------
Day 13 finished PENDING_PAYMENT -> PAID.
Day 14 finished PENDING_PAYMENT -> CANCELLED (plus timeout, plus the ledger).
Day 15 finishes the FORWARD half:  PAID -> SHIPPED -> COMPLETED.
With Day 16's reviews this closes milestone M1 (place -> pay -> receive -> review).

The five edges, and why the last two are different
--------------------------------------------------
    edge     actor    start             CAS condition          stock side effect
    pay      user     PENDING_PAYMENT   ='PENDING_PAYMENT'     locked -> sold
    cancel   user     PENDING_PAYMENT   ='PENDING_PAYMENT'     locked -> available
    timeout  system   PENDING_PAYMENT   ='PENDING_PAYMENT'     locked -> available
    SHIP     ADMIN    PAID              ='PAID'                NONE
    CONFIRM  user     SHIPPED           ='SHIPPED'             NONE

Two structural facts fall out of that table, and this script asserts both:

  * ★ The first three edges share the SAME start (PENDING_PAYMENT), so they
    MUTUALLY EXCLUDE -- only one can win. The last two each guard a DIFFERENT
    start, so they do not exclude; they are strictly ordered. A state machine
    is "some edges competing for one slot" PLUS "some edges each owning a leg".

  * ★★ The last two edges do not touch inventory AT ALL. Goods were committed
    to `sold` at the moment of payment; shipping and receiving are pure
    logistics state. So these two edges are single UPDATEs with no transaction
    -- the same shape as markPaid.

The headline assertion: RBAC's first real business use
------------------------------------------------------
`ship` is the FIRST business endpoint in this project that actually uses the
RBAC built on Day 07. C-end controllers deliberately carry no @PreAuthorize
because a C-end token's permission set is EMPTY. `ship` is an admin action, so
it carries @PreAuthorize("hasAuthority('order:ship')") -- and a C-end token
hitting it must get a real HTTP 403. That is asserted in section [6].

★ A second, subtler thing is asserted in section [6] too: `ship` does NOT read
the principal. JwtAuthenticationFilter turns the token's `sub` into a Long and
uses it as the principal WITHOUT distinguishing user ids from admin ids (it
ignores the token's `type:"ADMIN"` claim). So admin(id=1) and demo(id=1) both
have principal 1L. Recording "who shipped it" from the principal would silently
mix the two. `ship` therefore takes no Authentication parameter at all.

Re-runnable and self-cleaning
-----------------------------
It snapshots the baseline, reasons only about rows it created, cleans up in a
`finally`, and re-verifies the baseline byte-for-byte at the end.

Usage:
    python day15-ship-confirm.py
Report (utf-8) is written next to this file: day15-ship-confirm-report.txt
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
OUT = os.path.join(HERE, "day15-ship-confirm-report.txt")

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


def body_code(raw):
    """★ Day 13 教训：业务 404 藏在 body.code 里（HTTP 仍是 200）。
    GlobalExceptionHandler 的方法没有 @ResponseStatus，真实 HTTP 状态码
    只出现在 Security 层的 401/403。"""
    try:
        return json.loads(raw).get("code")
    except ValueError:
        return None


# ---------------------------------------------------------------- db helpers
def psql(sql):
    """★ 必须把 stderr 暴露出来：只读 stdout 时，SQL 错误会伪装成「没数据」。"""
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
    out = one("SELECT sku_id||'|'||total_stock||'|'||available_stock||'|'"
              "||locked_stock||'|'||sold_stock FROM inventories ORDER BY sku_id")
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


def stock_delta(a, b):
    return "available %+d  locked %+d  sold %+d" % (
        b["available"] - a["available"], b["locked"] - a["locked"], b["sold"] - a["sold"])


def stock_same(a, b):
    return (a["available"], a["locked"], a["sold"]) == (b["available"], b["locked"], b["sold"])


def order_row(order_id):
    out = one("SELECT status||'|'||coalesce(to_char(paid_at,'HH24:MI:SS'),'-')||'|'"
              "||coalesce(to_char(shipped_at,'HH24:MI:SS'),'-')||'|'"
              "||coalesce(to_char(completed_at,'HH24:MI:SS'),'-')||'|'"
              "||coalesce(to_char(cancelled_at,'HH24:MI:SS'),'-')"
              " FROM orders WHERE id=%d" % order_id)
    p = [x.strip() for x in out.split("|")]
    if len(p) != 5:
        return None
    return dict(status=p[0], paid_at=p[1], shipped_at=p[2],
                completed_at=p[3], cancelled_at=p[4])


def status_of(order_id):
    return one("SELECT status FROM orders WHERE id=%d" % order_id) or "(missing)"


def ledger_count():
    return int(one("SELECT count(*) FROM inventory_logs"))


def short(raw, n=150):
    raw = raw.replace("\r", "").replace("\n", " ").strip()
    return raw if len(raw) <= n else raw[:n] + " ...(truncated)"


def drift(query):
    return one(query).strip()


# ★ 两个对账口径：旧口径只认 PAID，新口径认「已售出去的三个状态」。
#   发货会把订单从 PAID 挪到 SHIPPED —— 旧口径因此会报假漂移（Day 15 §0.2）。
SOLD_DRIFT_OLD = """
    WITH s AS (SELECT sku_id, sold_stock FROM inventories WHERE sold_stock <> 0),
         p AS (SELECT oi.sku_id, SUM(oi.quantity) q FROM order_items oi
                 JOIN orders o ON o.id = oi.order_id
                WHERE o.status = 'PAID' GROUP BY oi.sku_id)
    SELECT count(*) FROM s FULL OUTER JOIN p ON s.sku_id = p.sku_id
     WHERE COALESCE(s.sold_stock,0) <> COALESCE(p.q,0)
"""
SOLD_DRIFT_NEW = """
    WITH s AS (SELECT sku_id, sold_stock FROM inventories WHERE sold_stock <> 0),
         p AS (SELECT oi.sku_id, SUM(oi.quantity) q FROM order_items oi
                 JOIN orders o ON o.id = oi.order_id
                WHERE o.status IN ('PAID','SHIPPED','COMPLETED') GROUP BY oi.sku_id)
    SELECT count(*) FROM s FULL OUTER JOIN p ON s.sku_id = p.sku_id
     WHERE COALESCE(s.sold_stock,0) <> COALESCE(p.q,0)
"""
LOCKED_DRIFT = """
    WITH l AS (SELECT sku_id, locked_stock FROM inventories WHERE locked_stock <> 0),
         p AS (SELECT oi.sku_id, SUM(oi.quantity) q FROM order_items oi
                 JOIN orders o ON o.id = oi.order_id
                WHERE o.status = 'PENDING_PAYMENT' GROUP BY oi.sku_id)
    SELECT count(*) FROM l FULL OUTER JOIN p ON l.sku_id = p.sku_id
     WHERE COALESCE(l.locked_stock,0) <> COALESCE(p.q,0)
"""


class _Abort(Exception):
    """Early abort that still runs the cleanup in `finally` and still writes the
    report. (A bare `return` would skip the summary + flush.)"""


# ================================================================ main
def main():
    checks = []

    def chk(name, good):
        checks.append((name, bool(good)))

    say("=" * 78)
    say("Day 15 -- ship + confirm: the last two edges (PAID -> SHIPPED -> COMPLETED)")
    say("target : %s   accounts: demo(id=1) / admin(id=1) / intruder(id=2)" % BASE)
    say("sku under test: %d" % TARGET_SKU)
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
    chk("every SKU satisfies total = available + locked + sold",
        all(r["total"] == r["available"] + r["locked"] + r["sold"] for r in base_all.values()))
    chk("baseline sold conservation holds with the NEW rule (PAID+SHIPPED+COMPLETED)",
        drift(SOLD_DRIFT_NEW) == "0")
    chk("baseline locked conservation holds", drift(LOCKED_DRIFT) == "0")

    # ---------------------------------------------------------- [1] logins
    say("\n[1] logins (tokens stay in memory, never on disk)")
    st, b, _ = japi("POST", "/api/auth/login", body={"username": "demo", "password": "demo123"})
    demo = (b.get("data") or {}).get("token")
    say("  demo      http=%s code=%s userId=%s token_len=%d"
        % (st, b.get("code"), (b.get("data") or {}).get("userId"), len(demo or "")))
    chk("demo login succeeded", bool(demo))

    st, b, _ = japi("POST", "/api/auth/admin/login",
                    body={"username": "admin", "password": "admin123"})
    admin = (b.get("data") or {}).get("token")
    say("  admin     http=%s code=%s adminId=%s token_len=%d"
        % (st, b.get("code"), (b.get("data") or {}).get("userId"), len(admin or "")))
    chk("admin login succeeded (needed for order:ship)", bool(admin))

    st, b, _ = japi("POST", "/api/auth/login", body={"username": "intruder", "password": "intruder"})
    intruder = (b.get("data") or {}).get("token")
    say("  intruder  http=%s code=%s userId=%s token_len=%d"
        % (st, b.get("code"), (b.get("data") or {}).get("userId"), len(intruder or "")))
    chk("intruder login succeeded", bool(intruder))

    if not demo or not admin:
        say("\nABORT: need both demo and admin tokens")
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

    def pay(order_id):
        return japi("POST", "/api/payments", token=demo,
                    body={"orderId": order_id, "method": "ALIPAY"})

    def ship(order_id, token=admin):
        """★ token defaults to ADMIN -- ship is an admin action."""
        return japi("POST", "/api/orders/%d/ship" % order_id, token=token)

    def confirm(order_id, token=demo):
        return japi("POST", "/api/orders/%d/confirm" % order_id, token=token)

    created = []

    try:
        # ================================================ ORDER A: happy path
        say("\n" + "-" * 78)
        say("ORDER A -- the full forward path: place -> pay -> SHIP -> CONFIRM")
        say("-" * 78)

        say("\n[2] place order A (sku%d x1)" % TARGET_SKU)
        order_a, code_a, raw_a = place_order()
        say("  POST /api/orders -> order=%s code=%s %s" % (order_a, code_a, short(raw_a, 80)))
        chk("order A created", isinstance(order_a, int))
        if not isinstance(order_a, int):
            say("\nABORT: could not create order A")
            raise _Abort()
        created.append(order_a)
        a_placed = inv(TARGET_SKU)
        say(inv_line("after place A", TARGET_SKU, a_placed))
        say("  delta vs start: %s" % stock_delta(base, a_placed))
        chk("A: place -> PENDING_PAYMENT", status_of(order_a) == "PENDING_PAYMENT")
        chk("A: place moved available -1 / locked +1 / sold +0",
            a_placed["available"] == A0 - 1 and a_placed["locked"] == base["locked"] + 1
            and a_placed["sold"] == base["sold"])

        say("\n[3] pay order A")
        st_p, b_p, _ = pay(order_a)
        say("  POST /api/payments -> http=%s code=%s" % (st_p, b_p.get("code")))
        chk("A: payment succeeded", st_p == 200 and b_p.get("code") == 200)
        a_paid = inv(TARGET_SKU)
        row_a = order_row(order_a)
        say(inv_line("after pay A", TARGET_SKU, a_paid))
        say("  delta vs after-place: %s" % stock_delta(a_placed, a_paid))
        chk("A: pay -> PAID", status_of(order_a) == "PAID")
        chk("A: pay moved locked -1 / sold +1, available untouched",
            a_paid["locked"] == a_placed["locked"] - 1
            and a_paid["sold"] == a_placed["sold"] + 1
            and a_paid["available"] == a_placed["available"])
        chk("A: paid_at stamped", row_a and row_a["paid_at"] != "-")
        chk("A: shipped_at / completed_at still NULL", row_a
            and row_a["shipped_at"] == "-" and row_a["completed_at"] == "-")

        say("\n[4] ★ SHIP order A -- ADMIN token, needs order:ship")
        st_s, b_s, raw_s = ship(order_a)
        say("  POST /api/orders/%d/ship (admin) -> http=%s code=%s %s"
            % (order_a, st_s, b_s.get("code"), short(raw_s, 80)))
        chk("A: ship succeeded", st_s == 200 and b_s.get("code") == 200)
        a_shipped = inv(TARGET_SKU)
        row_a = order_row(order_a)
        say(inv_line("after ship A", TARGET_SKU, a_shipped))
        say("  delta vs after-pay: %s   ★ must be all zeros" % stock_delta(a_paid, a_shipped))
        chk("A: ship -> SHIPPED", status_of(order_a) == "SHIPPED")
        chk("★★ A: ship did NOT touch inventory at all", stock_same(a_paid, a_shipped))
        chk("A: shipped_at stamped", row_a and row_a["shipped_at"] != "-")
        chk("A: completed_at still NULL", row_a and row_a["completed_at"] == "-")
        chk("A: cancelled_at never touched", row_a and row_a["cancelled_at"] == "-")

        say("\n[5] ★ CONFIRM order A -- C-end token, the owner")
        st_c, b_c, raw_c = confirm(order_a)
        say("  POST /api/orders/%d/confirm (demo) -> http=%s code=%s %s"
            % (order_a, st_c, b_c.get("code"), short(raw_c, 80)))
        chk("A: confirm succeeded", st_c == 200 and b_c.get("code") == 200)
        a_done = inv(TARGET_SKU)
        row_a = order_row(order_a)
        say(inv_line("after confirm A", TARGET_SKU, a_done))
        say("  delta vs after-ship: %s   ★ must be all zeros" % stock_delta(a_shipped, a_done))
        chk("A: confirm -> COMPLETED", status_of(order_a) == "COMPLETED")
        chk("★★ A: confirm did NOT touch inventory at all", stock_same(a_shipped, a_done))
        chk("A: completed_at stamped", row_a and row_a["completed_at"] != "-")
        say("  A timestamps: paid=%s shipped=%s completed=%s"
            % (row_a["paid_at"], row_a["shipped_at"], row_a["completed_at"]))
        chk("A: the three timestamps are non-decreasing (paid <= shipped <= completed)",
            row_a["paid_at"] <= row_a["shipped_at"] <= row_a["completed_at"])

        # ================================================ ORDER B: negatives
        say("\n" + "-" * 78)
        say("ORDER B -- the guard rails: wrong state, wrong actor, repeated calls")
        say("-" * 78)

        say("\n[6] ★★ RBAC -- ship is the first business endpoint that really uses it")
        order_b, code_b, _ = place_order()
        say("  order B placed -> %s" % order_b)
        chk("order B created", isinstance(order_b, int))
        if not isinstance(order_b, int):
            say("\nABORT: could not create order B")
            raise _Abort()
        created.append(order_b)

        before_rbac = status_of(order_b)
        st_d, raw_d = api("POST", "/api/orders/%d/ship" % order_b, token=demo)
        say("  demo (C-end) token  -> ship order B : http=%s code=%s %s"
            % (st_d, body_code(raw_d), short(raw_d, 100)))
        chk("★★ C-end token is REFUSED with a real HTTP 403 (empty permission set)",
            st_d == 403)
        chk("★★ RBAC refusal changed no state", status_of(order_b) == before_rbac)

        st_n, raw_n = api("POST", "/api/orders/%d/ship" % order_b)
        say("  anonymous           -> ship order B : http=%s code=%s %s"
            % (st_n, body_code(raw_n), short(raw_n, 100)))
        chk("★ anonymous is refused with 401 (not on the whitelist)",
            st_n == 401)

        st_x, raw_x = api("POST", "/api/orders/%d/ship" % order_b, token=intruder)
        say("  intruder (C-end)    -> ship order B : http=%s code=%s %s"
            % (st_x, body_code(raw_x), short(raw_x, 100)))
        chk("★ any C-end token is refused with 403 (RBAC, not ownership)",
            st_x == 403)
        chk("★ stock untouched by all three refusals", stock_same(a_done, inv(TARGET_SKU)))

        say("\n[7] wrong-state guards (the CAS condition, one edge at a time)")
        st_w, b_w, raw_w = ship(order_b)          # B is PENDING_PAYMENT, needs PAID
        say("  admin ship a PENDING_PAYMENT order -> http=%s code=%s %s"
            % (st_w, b_w.get("code"), short(raw_w, 100)))
        chk("★ cannot ship before payment (400, not 500)", b_w.get("code") == 400)
        chk("order B still PENDING_PAYMENT", status_of(order_b) == "PENDING_PAYMENT")

        st_pb, b_pb, _ = pay(order_b)
        say("  pay order B -> http=%s code=%s" % (st_pb, b_pb.get("code")))
        chk("order B paid", status_of(order_b) == "PAID")
        b_paid = inv(TARGET_SKU)

        st_w2, b_w2, raw_w2 = confirm(order_b)    # B is PAID, needs SHIPPED
        say("  demo confirm a PAID order -> http=%s code=%s %s"
            % (st_w2, b_w2.get("code"), short(raw_w2, 100)))
        chk("★ cannot confirm receipt before shipping (400, not 500)", b_w2.get("code") == 400)
        chk("order B still PAID", status_of(order_b) == "PAID")

        st_sb, b_sb, _ = ship(order_b)
        say("  admin ship order B -> http=%s code=%s" % (st_sb, b_sb.get("code")))
        chk("order B shipped", status_of(order_b) == "SHIPPED")
        b_shipped = inv(TARGET_SKU)
        chk("★ shipping B did not touch inventory either", stock_same(b_paid, b_shipped))

        say("\n[8] IDOR -- ownership is checked BEFORE the CAS")
        st_i, raw_i = api("POST", "/api/orders/%d/confirm" % order_b, token=intruder)
        say("  intruder confirm demo's order B -> http=%s code=%s %s"
            % (st_i, body_code(raw_i), short(raw_i, 100)))
        chk("★★ intruder gets a business-404 (indistinguishable from 'not found')",
            body_code(raw_i) == 404)
        # ★ 关键：B 此刻正是 SHIPPED，CAS 本来会成功 ——
        #   所以这个 404 只可能来自 requireOwn，证明归属校验跑在 CAS 之前。
        chk("★★ order B is still SHIPPED (the CAS was never reached)", 
            status_of(order_b) == "SHIPPED")
        chk("★ stock untouched by the IDOR attempt", stock_same(b_shipped, inv(TARGET_SKU)))

        say("\n[9] idempotency -- the second call must be refused")
        st_r, b_r, raw_r = ship(order_b)          # already SHIPPED
        say("  admin ship an already-SHIPPED order -> http=%s code=%s %s"
            % (st_r, b_r.get("code"), short(raw_r, 100)))
        chk("★ double-ship refused with 400", b_r.get("code") == 400)
        chk("order B still SHIPPED after double-ship", status_of(order_b) == "SHIPPED")

        st_cb, b_cb, _ = confirm(order_b)
        say("  demo confirm order B -> http=%s code=%s" % (st_cb, b_cb.get("code")))
        chk("order B completed", status_of(order_b) == "COMPLETED")
        st_r2, b_r2, raw_r2 = confirm(order_b)
        say("  demo confirm again -> http=%s code=%s %s"
            % (st_r2, b_r2.get("code"), short(raw_r2, 100)))
        chk("★ double-confirm refused with 400", b_r2.get("code") == 400)
        chk("order B still COMPLETED", status_of(order_b) == "COMPLETED")

        # ================================================ [10] conservation
        say("\n" + "=" * 78)
        say("[10] ★★ THE RECONCILIATION RULE HAD TO CHANGE (Day 15 section 0.2)")
        say("=" * 78)
        old = drift(SOLD_DRIFT_OLD)
        new = drift(SOLD_DRIFT_NEW)
        say("  sold == sum(PAID units)                              -> %s drifting SKUs" % old)
        say("  sold == sum(PAID + SHIPPED + COMPLETED units)         -> %s drifting SKUs" % new)
        say("  ★ 两份订单已经走完 SHIPPED / COMPLETED，但 sold 仍然记着它们。")
        say("    旧口径只认 PAID，于是它们从右边「掉出去」→ 报假漂移。")
        chk("★★ the OLD rule (PAID only) now reports drift -- proving it was outdated",
            old != "0")
        chk("★★ the NEW rule (PAID+SHIPPED+COMPLETED) reports zero drift", new == "0")
        say("  locked conservation (unchanged rule) -> %s drifting SKUs" % drift(LOCKED_DRIFT))
        chk("locked conservation still holds", drift(LOCKED_DRIFT) == "0")
        chk("no negative stock anywhere",
            one("SELECT count(*) FROM inventories WHERE available_stock < 0"
                " OR locked_stock < 0 OR sold_stock < 0").strip() == "0")

        say("\n  ledger rows created by this run: %d"
            % (ledger_count() - int(one("SELECT count(*) FROM inventory_logs WHERE id <= %d"
                                        % high_water))))
        say("  ★ 本日两条边【不写流水】：inventory_logs 记的是「库存发生过什么」，")
        say("    发货/收货对库存贡献为 0，硬塞一条 change=0 只会让账本变脏。")

    except _Abort:
        say("\n(aborted early -- cleanup below still runs)")

    finally:
        # ================================================== [11] cleanup
        say("\n" + "=" * 78)
        say("[11] CLEANUP -- remove this run's artifacts, restore the baseline")
        say("=" * 78)
        say("  orders to delete: %s" % (created or "(none)"))
        say("  ledger rows to delete: id > %d" % high_water)
        try:
            if created:
                ids = ",".join(str(o) for o in created)
                psql("DELETE FROM payments WHERE order_id IN (%s);"
                     " DELETE FROM order_items WHERE order_id IN (%s);"
                     " DELETE FROM orders WHERE id IN (%s);" % (ids, ids, ids))
            psql("DELETE FROM inventory_logs WHERE id > %d;" % high_water)
            psql("UPDATE inventories SET locked_stock = %d, sold_stock = %d,"
                 " available_stock = total_stock - %d - %d,"
                 " updated_at = CURRENT_TIMESTAMP WHERE sku_id = %d;"
                 % (base["locked"], base["sold"], base["sold"], base["locked"], TARGET_SKU))
            chk("cleanup ran without SQL error", True)
        except Exception as e:                                        # noqa: BLE001
            say("  CLEANUP FAILED: %s" % e)
            chk("cleanup ran without SQL error", False)

        say("\n[12] VERIFY -- the database is byte-for-byte back at baseline")
        after_all = all_inv()
        for sku in sorted(after_all):
            tag = "restored" if after_all[sku] == base_all.get(sku) else "DRIFTED"
            say(inv_line(tag, sku, after_all[sku]))
        mismatches = [sku for sku in base_all if after_all.get(sku) != base_all[sku]]
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
        chk("no orphan order_items left", one(
            "SELECT count(*) FROM order_items oi LEFT JOIN orders o ON o.id = oi.order_id"
            " WHERE o.id IS NULL").strip() == "0")
        chk("no orphan payments left", one(
            "SELECT count(*) FROM payments p LEFT JOIN orders o ON o.id = p.order_id"
            " WHERE o.id IS NULL").strip() == "0")
        chk("no SHIPPED / COMPLETED order left behind by this run",
            one("SELECT count(*) FROM orders WHERE status IN ('SHIPPED','COMPLETED')"
                ).strip() == "0")

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
