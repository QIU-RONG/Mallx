# -*- coding: utf-8 -*-
"""
Day 14 Step 1 -- CANCEL an order (state machine reverse edge + stock give-back).

Day 13 only let orders.status move FORWARD:
    PENDING_PAYMENT --pay--> PAID   (inventory: locked -> sold)
This step adds the other edge:
    PENDING_PAYMENT --cancel--> CANCELLED   (inventory: locked -> available)

cancel() is a mirror image of pay():
    (1) ownership    SELECT ... WHERE id AND user_id   -> 404 (same wording as pay)
    (2) items        read order_items                  -> 500 if empty
    (3) CAS          WHERE status='PENDING_PAYMENT'    -> 400 if it lost the race
    (4) stock        releaseLocked (locked -> available),升序 by skuId

What this script must prove, in order of importance:

  * ★ available_stock comes BACK. Opening the order moved available -1 / locked +1;
    cancelling must move it back to exactly where it started, with sold untouched.
    This is the whole point: releaseLocked is the exact inverse of deductStock.
  * ★ Write-IDOR is really blocked. `intruder` cancelling demo's order must get the
    SAME 404 as a non-existent id -- AND the order must still be PENDING_PAYMENT
    with its stock still locked afterwards. A status code alone proves nothing;
    the database has to agree.
  * ★ Cancel is not idempotent: the second call gets 400 (which is why the
    endpoint is POST, not PUT).
  * A PAID order cannot be cancelled (400) -- the two exits really are exclusive.

Usage:
    python day14-cancel-verify.py
Report (utf-8) is written next to this file: day14-cancel-verify-report.txt
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
OUT = os.path.join(HERE, "day14-cancel-verify-report.txt")

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
      报 `502 upstream connect failed (os error 10061)` —— 看起来像服务挂了。
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
    p = subprocess.run(
        [DOCKER, "exec", "-i", "-e", "PGCLIENTENCODING=UTF8",
         "mallx-postgres", "psql", "-U", "mallx", "-d", "mallx",
         "-t", "-A", "-F", "|", "-c", sql],
        capture_output=True)
    return p.stdout.decode("utf-8", "replace").strip()


def one(sql):
    """Single scalar. ⚠️ docker exec 回传的行尾带 \\r —— 不 strip 比对照样为假。"""
    return psql(sql).strip()


def inv(sku):
    out = one("SELECT total_stock||','||available_stock||','||locked_stock||','||sold_stock"
              "||','||(total_stock=available_stock+locked_stock+sold_stock)"
              " FROM inventories WHERE sku_id=%d" % sku)
    p = [x.strip() for x in out.split(",")]
    return dict(total=int(p[0]), available=int(p[1]), locked=int(p[2]),
                sold=int(p[3]), id_ok=p[4].lower() in ("t", "true"))


def inv_line(tag, sku, r):
    return "  %-16s sku%d  total=%3d  available=%3d  locked=%3d  sold=%3d  identity=%s" % (
        tag, sku, r["total"], r["available"], r["locked"], r["sold"],
        "OK" if r["id_ok"] else "BROKEN")


def delta(a, b):
    return "available %+d  locked %+d  sold %+d" % (
        b["available"] - a["available"], b["locked"] - a["locked"], b["sold"] - a["sold"])


def order_status(order_id):
    return one("SELECT status FROM orders WHERE id=%d" % order_id) or "(missing)"


def cancelled_at(order_id):
    return one("SELECT coalesce(cancelled_at::text,'NULL') FROM orders WHERE id=%d" % order_id)


def short(raw, n=200):
    raw = raw.replace("\r", "").replace("\n", " ").strip()
    return raw if len(raw) <= n else raw[:n] + " ...(truncated)"


# ================================================================ main
def main():
    checks = []

    def chk(name, good):
        checks.append((name, bool(good)))

    say("=" * 78)
    say("Day 14 Step 1 -- cancel an order (CANCELLED + locked -> available)")
    say("target : %s   account: demo(id=1) / intruder(id=2)" % BASE)
    say("=" * 78)

    # ---------------------------------------------------------- [0] baseline
    say("\n[0] BASELINE (psql)")
    base = inv(TARGET_SKU)
    base_orders = int(one("SELECT count(*) FROM orders"))
    base_pending = int(one("SELECT count(*) FROM orders WHERE status='PENDING_PAYMENT'"))
    max_order_id = int(one("SELECT max(id) FROM orders"))
    paid_order = one("SELECT id FROM orders WHERE status='PAID' AND user_id=1 ORDER BY id LIMIT 1")
    say(inv_line("stock", TARGET_SKU, base))
    say("  orders=%d  PENDING_PAYMENT=%d  max_order_id=%d  a PAID order to probe=%s"
        % (base_orders, base_pending, max_order_id, paid_order))
    chk("baseline identity holds for sku%d" % TARGET_SKU, base["id_ok"])

    # ---------------------------------------------------------- [1] anonymous
    say("\n[1] anonymous POST /api/orders/1/cancel")
    st, raw = api("POST", "/api/orders/1/cancel")
    say("  http=%s code=%s %s" % (st, body_code(raw), short(raw, 120)))
    say("  ★ 这是 Security 层写的响应（过滤器），所以是【真 HTTP 401】")
    chk("anonymous rejected with a REAL HTTP 401", st == 401)

    # ---------------------------------------------------------- [2] login
    say("\n[2] login demo + intruder (tokens stay in memory, never on disk)")
    st, b, _ = japi("POST", "/api/auth/login", body={"username": "demo", "password": "demo123"})
    demo = (b.get("data") or {}).get("token")
    st2, b2, _ = japi("POST", "/api/auth/login", body={"username": "intruder", "password": "intruder"})
    intr = (b2.get("data") or {}).get("token")
    say("  demo     http=%s code=%s userId=%s token_len=%d" % (
        st, b.get("code"), (b.get("data") or {}).get("userId"), len(demo or "")))
    say("  intruder http=%s code=%s userId=%s token_len=%d" % (
        st2, b2.get("code"), (b2.get("data") or {}).get("userId"), len(intr or "")))
    chk("both logins succeeded", bool(demo) and bool(intr))
    if not (demo and intr):
        say("\nABORT: no token")
        flush()
        return 1

    # ---------------------------------------------------------------- helpers
    def place_order():
        """Put sku4 x1 in the cart, select it, and create an order. Returns order id."""
        st_, b_, _ = japi("GET", "/api/cart", token=demo)
        target = None
        for it in ((b_.get("data") or {}).get("items") or []):
            if it.get("skuId") == TARGET_SKU:
                target = it
        if target is None:
            say("    sku%d not in cart -> POST /api/cart {skuId:%d, quantity:1}" % (TARGET_SKU, TARGET_SKU))
            japi("POST", "/api/cart", token=demo, body={"skuId": TARGET_SKU, "quantity": 1})
            st_, b_, _ = japi("GET", "/api/cart", token=demo)
            for it in ((b_.get("data") or {}).get("items") or []):
                if it.get("skuId") == TARGET_SKU:
                    target = it
        if target is None:
            return None
        japi("PUT", "/api/cart/%s/selected" % target["id"], token=demo, body={"selected": True})
        st_, b_, _ = japi("POST", "/api/orders", token=demo, body={"addressId": ADDRESS_ID})
        return b_.get("data") if st_ == 200 and isinstance(b_.get("data"), int) else None

    # ---------------------------------------------------------- [3] target A
    say("\n[3] build target A: place an order that stays PENDING_PAYMENT")
    order_a = place_order()
    say("  new order id = %s (must be > %d)" % (order_a, max_order_id))
    chk("order A created", isinstance(order_a, int))
    if not isinstance(order_a, int):
        say("\nABORT: could not create order A")
        flush()
        return 1
    chk("order A id is fresh", order_a > max_order_id)
    chk("order A status is PENDING_PAYMENT", order_status(order_a) == "PENDING_PAYMENT")

    after_order = inv(TARGET_SKU)
    say("[4] stock right after ordering -- the LOCK happens here")
    say(inv_line("after order", TARGET_SKU, after_order))
    say("  delta vs baseline: %s" % delta(base, after_order))
    chk("ordering locked the stock: available -1, locked +1, sold +0",
        after_order["available"] == base["available"] - 1
        and after_order["locked"] == base["locked"] + 1
        and after_order["sold"] == base["sold"])

    # ---------------------------------------------------------- [5] cancel A
    say("\n[5] POST /api/orders/%d/cancel  (demo cancels his own order)" % order_a)
    st, b, raw = japi("POST", "/api/orders/%d/cancel" % order_a, token=demo)
    say("  http=%s code=%s message=%s data=%s" % (
        st, b.get("code"), b.get("message"), json.dumps(b.get("data"))))
    chk("cancel succeeded (HTTP 200 + code 200)", st == 200 and b.get("code") == 200)
    chk("cancel returns Result<Void> (data is null)", b.get("data") is None)

    say("\n[6] GET /api/orders/%d  (must be CANCELLED, cancelledAt written, paidAt still null)" % order_a)
    st, b, _ = japi("GET", "/api/orders/%s" % order_a, token=demo)
    od = b.get("data") or {}
    say("  http=%s status=%s paidAt=%s cancelledAt=%s"
        % (st, od.get("status"), od.get("paidAt"), od.get("cancelledAt")))
    say("  psql  : status=%s  cancelled_at=%s" % (order_status(order_a), cancelled_at(order_a)))
    chk("order A is CANCELLED", od.get("status") == "CANCELLED")
    chk("cancelledAt is populated", od.get("cancelledAt") is not None)
    chk("paidAt was NOT touched by cancel", od.get("paidAt") is None)

    # ---------------------------------------------------------- [7] give-back
    say("\n[7] ★★ STOCK GIVE-BACK -- releaseLocked is the exact inverse of deductStock")
    after_cancel = inv(TARGET_SKU)
    say(inv_line("after cancel", TARGET_SKU, after_cancel))
    say("  delta vs after-order : %s" % delta(after_order, after_cancel))
    say("  delta vs baseline    : %s   <-- must be 0/0/0" % delta(base, after_cancel))
    chk("locked went BACK to baseline", after_cancel["locked"] == base["locked"])
    chk("available went BACK to baseline", after_cancel["available"] == base["available"])
    chk("sold untouched by cancel", after_cancel["sold"] == base["sold"])
    chk("identity still holds", after_cancel["id_ok"])

    # ---------------------------------------------------------- [8] repeat
    say("\n[8] DUPLICATE CANCEL -- same order again (this is why the verb is POST, not PUT)")
    st, b, _ = japi("POST", "/api/orders/%d/cancel" % order_a, token=demo)
    say("  http=%s code=%s message=%s" % (st, b.get("code"), b.get("message")))
    chk("duplicate cancel rejected: HTTP 200 + code 400",
        st == 200 and b.get("code") == 400)
    chk("...with the expected wording", "不允许取消" in (b.get("message") or ""))
    chk("stock not moved again by the rejected attempt", inv(TARGET_SKU) == after_cancel)

    # ---------------------------------------------------------- [9] target B
    say("\n[9] build target B (for the write-IDOR probe)")
    order_b = place_order()
    say("  new order id = %s -> status=%s" % (order_b, order_status(order_b)))
    chk("order B created and PENDING_PAYMENT", order_status(order_b) == "PENDING_PAYMENT")
    if not isinstance(order_b, int):
        say("\nABORT: could not create order B")
        flush()
        return 1
    locked_before_idor = inv(TARGET_SKU)

    # ---------------------------------------------------------- [10] IDOR
    say("\n[10] ★★ WRITE-IDOR -- intruder tries to cancel demo's order")
    st1, raw_foreign = api("POST", "/api/orders/%s/cancel" % order_b, token=intr)
    st2, raw_absent = api("POST", "/api/orders/99999999/cancel", token=intr)
    say("  POST /api/orders/%s/cancel        (intruder) -> http=%s code=%s %s" % (
        order_b, st1, body_code(raw_foreign), short(raw_foreign, 120)))
    say("  POST /api/orders/99999999/cancel  (intruder) -> http=%s code=%s %s" % (
        st2, body_code(raw_absent), short(raw_absent, 120)))
    chk("intruder gets business-404 (HTTP 200 + code 404)",
        st1 == 200 and body_code(raw_foreign) == 404)
    chk("foreign-404 == absent-404 (byte identical)",
        raw_foreign.strip() == raw_absent.strip())

    say("\n[11] ★★ ...and the database must AGREE (a status code alone proves nothing)")
    st_after = order_status(order_b)
    locked_after_idor = inv(TARGET_SKU)
    say("  order B status after the intruder's attempt : %s" % st_after)
    say("  cancelled_at                                : %s" % cancelled_at(order_b))
    say(inv_line("after IDOR", TARGET_SKU, locked_after_idor))
    chk("order B is STILL PENDING_PAYMENT (write really was blocked)",
        st_after == "PENDING_PAYMENT")
    chk("cancelled_at is still NULL", cancelled_at(order_b) == "NULL")
    chk("stock untouched by the blocked write (still locked)", locked_after_idor == locked_before_idor)

    say("\n[12] demo cancels order B for real (proves the block was ownership, not breakage)")
    st, b, _ = japi("POST", "/api/orders/%d/cancel" % order_b, token=demo)
    say("  http=%s code=%s status now=%s" % (st, b.get("code"), order_status(order_b)))
    chk("demo's own cancel of B succeeded", st == 200 and b.get("code") == 200)
    chk("stock returned to baseline again", inv(TARGET_SKU) == base)

    # ---------------------------------------------------------- [13] PAID
    if paid_order:
        say("\n[13] cancel an already-PAID order (#%s) -- the two exits are exclusive" % paid_order)
        st, b, _ = japi("POST", "/api/orders/%s/cancel" % paid_order, token=demo)
        say("  http=%s code=%s message=%s" % (st, b.get("code"), b.get("message")))
        chk("PAID order cannot be cancelled (400)",
            st == 200 and b.get("code") == 400)
        say("  psql: status still %s, cancelled_at=%s"
            % (order_status(int(paid_order)), cancelled_at(int(paid_order))))
        chk("PAID order untouched", order_status(int(paid_order)) == "PAID"
            and cancelled_at(int(paid_order)) == "NULL")
    else:
        say("\n[13] (no PAID order owned by demo -- skipped)")

    # ---------------------------------------------------------- [14] odd ids
    say("\n[14] edge ids")
    st, b, _ = japi("POST", "/api/orders/99999999/cancel", token=demo)
    say("  POST /api/orders/99999999/cancel  (demo) -> http=%s code=%s message=%s"
        % (st, b.get("code"), b.get("message")))
    chk("non-existent id -> 404", st == 200 and b.get("code") == 404)

    st, b, _ = japi("POST", "/api/orders/abc/cancel", token=demo)
    say("  POST /api/orders/abc/cancel       (demo) -> http=%s code=%s message=%s"
        % (st, b.get("code"), b.get("message")))
    chk("/abc -> code=400 (path variable type mismatch)", st == 200 and b.get("code") == 400)

    # ---------------------------------------------------------- [15] audit
    say("\n[15] FINAL DATABASE AUDIT (psql)")
    fin_orders = int(one("SELECT count(*) FROM orders"))
    bad_identity = one("SELECT coalesce(string_agg(sku_id::text, ','), '-') FROM inventories "
                       "WHERE total_stock <> available_stock + locked_stock + sold_stock")
    neg = one("SELECT coalesce(string_agg(sku_id::text, ','), '-') FROM inventories "
              "WHERE available_stock < 0 OR locked_stock < 0 OR sold_stock < 0")
    # ★ 业务守恒：本次校准之后它必须【一直是】0 行
    drift = one("SELECT coalesce(string_agg(t.sku_id::text, ','), '-') FROM ("
                " SELECT i.sku_id FROM inventories i"
                " LEFT JOIN (SELECT oi.sku_id, sum(oi.quantity) AS want FROM order_items oi"
                "            JOIN orders o ON o.id=oi.order_id WHERE o.status='PENDING_PAYMENT'"
                "            GROUP BY oi.sku_id) l ON l.sku_id=i.sku_id"
                " LEFT JOIN (SELECT oi.sku_id, sum(oi.quantity) AS want FROM order_items oi"
                "            JOIN orders o ON o.id=oi.order_id WHERE o.status='PAID'"
                "            GROUP BY oi.sku_id) s ON s.sku_id=i.sku_id"
                " WHERE i.locked_stock <> coalesce(l.want,0) OR i.sold_stock <> coalesce(s.want,0)"
                ") t")
    say("  orders %d -> %d" % (base_orders, fin_orders))
    say("  broken identity (total<>a+l+s)      : %s" % bad_identity)
    say("  negative stock                      : %s" % neg)
    say("  ★ business-conservation drift (sku)  : %s   <-- 期望 '-'" % drift)
    say("  all 7 inventories:")
    for s in range(1, 8):
        say(inv_line("", s, inv(s)))
    chk("identity holds for ALL 7 SKUs", bad_identity == "-")
    chk("no negative stock anywhere", neg == "-")
    chk("★ business conservation still holds after the whole trip (no drift)", drift == "-")

    # ---------------------------------------------------------- verdict
    say("\n" + "=" * 78)
    say("ASSERTIONS")
    say("=" * 78)
    passed = 0
    for name, good in checks:
        say("  [%s] %s" % ("PASS" if good else "FAIL", name))
        passed += 1 if good else 0
    say("\nRESULT: %d/%d passed" % (passed, len(checks)))
    say("VERDICT: %s" % ("CANCEL CHAIN OK -- status CAS, stock give-back, write-IDOR hidden,"
                         " duplicate cancel rejected, PAID order refuses to cancel"
                         if passed == len(checks) else "NOT CLEAN -- see FAIL lines above"))
    flush()
    print("report -> %s   %d/%d passed" % (OUT, passed, len(checks)))
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                                                 # noqa: BLE001
        import traceback
        say("\nCRASH:\n" + traceback.format_exc())
        flush()
        raise
