# -*- coding: utf-8 -*-
"""
Day 13 Step 5 -- END-TO-END payment chain (the whole machine, one pass).

Steps 1-4 each built a part and tested it in isolation. This script is the
first time the parts run as ONE system:

    cart  ->  order (PENDING_PAYMENT)  ->  pay  ->  order (PAID)
          ->  inventory moves locked->sold  ->  duplicate pay rejected
          ->  payment record visible to its owner and to nobody else

The point is not "does pay() work" (step 2 proved that). The point is that
across module boundaries the transaction really is one transaction, the
Security context really does carry the right userId, and the stock identity
total = available + locked + sold survives the whole trip.

Two extra cases beyond the happy path:
  * order #2 -- the PENDING_PAYMENT leftover from Day 12 -> paid off here,
    which also gives a SECOND independent sample (sku 5, qty 3).
  * intruder -- must get 404 for both the new order and the new payment,
    and those 404 bodies must be BYTE-IDENTICAL to the "no such id" ones.

Evidence is read straight out of PostgreSQL through `docker exec`; the API is
never trusted to report on itself.

Usage:
    python day13-e2e.py
Report (utf-8) is written next to this file: day13-e2e-report.txt
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080"
DOCKER = r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
TARGET_SKU = 4          # MATE80-BLK-512 @ 6999.00, qty 1 sitting in demo's cart
ADDRESS_ID = 2          # demo's default address
LEFTOVER_ORDER = 2      # Day 12 PENDING_PAYMENT, sku 5 x3 = 19497.00
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "day13-e2e-report.txt")

_lines = []


def say(s=""):
    _lines.append(s)


def flush():
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(_lines) + "\n")


# ---------------------------------------------------------------- http helper
def api(method, path, token=None, body=None, timeout=60):
    """Return (http_status, raw_text). Proxy is explicitly disabled.

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
    return "  %-14s sku%d  total=%3d  available=%3d  locked=%3d  sold=%3d  identity=%s" % (
        tag, sku, r["total"], r["available"], r["locked"], r["sold"],
        "OK" if r["id_ok"] else "BROKEN")


def pay_rows(order_id):
    return int(one("SELECT count(*) FROM payments WHERE order_id=%d" % order_id))


def pay_seq():
    return int(one("SELECT last_value FROM payments_id_seq"))


def short(raw, n=300):
    raw = raw.replace("\r", "").replace("\n", " ").strip()
    return raw if len(raw) <= n else raw[:n] + " ...(truncated)"


# ================================================================ main
def main():
    checks = []

    def chk(name, good):
        checks.append((name, bool(good)))

    say("=" * 78)
    say("Day 13 Step 5 -- end-to-end payment chain")
    say("target : %s   account: demo(id=1) / intruder(id=2)" % BASE)
    say("=" * 78)

    # ---------------------------------------------------------- [0] baseline
    say("\n[0] BASELINE (psql)")
    base_inv4 = inv(TARGET_SKU)
    base_inv5 = inv(5)
    base_orders = int(one("SELECT count(*) FROM orders"))
    base_pays = int(one("SELECT count(*) FROM payments"))
    base_seq = pay_seq()
    cart_rows = one("SELECT coalesce(string_agg(id||':'||sku_id||':'||quantity||':'||selected, ' , '), '-')"
                    " FROM cart_items WHERE user_id=1")
    say(inv_line("stock", TARGET_SKU, base_inv4))
    say(inv_line("stock", 5, base_inv5))
    say("  orders=%d  payments=%d  payments_seq=%d" % (base_orders, base_pays, base_seq))
    say("  demo cart_items : %s" % cart_rows)
    # ★ 断言一律走【相对量】而不是绝对值 —— 脚本第一次跑过之后库存就变了，
    #   若写死 147/1/2，第二次跑必然「假失败」。E2E 脚本必须可重复执行。
    max_order_id = int(one("SELECT max(id) FROM orders"))
    say("  max order id = %d (new order must be greater)" % max_order_id)
    chk("baseline identity holds (sku4 + sku5)", base_inv4["id_ok"] and base_inv5["id_ok"])

    # ---------------------------------------------------------- [1] anonymous
    say("\n[1] anonymous GET /api/payments")
    st, body, _ = japi("GET", "/api/payments")
    say("  http=%s  body=%s" % (st, short(json.dumps(body, ensure_ascii=False))))
    chk("anonymous rejected with 401", st == 401)

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

    # ---------------------------------------------------------- [3] cart
    def cart_item_for(sku):
        st_, b_, _ = japi("GET", "/api/cart", token=demo)
        for it in ((b_.get("data") or {}).get("items") or []):
            if it.get("skuId") == sku:
                return it
        return None

    say("\n[3] GET /api/cart  (locate the sku%d row)" % TARGET_SKU)
    st, b, _ = japi("GET", "/api/cart", token=demo)
    items = (b.get("data") or {}).get("items") or []
    say("  http=%s items=%d  selectedQuantity=%s selectedAmount=%s" % (
        st, len(items), (b.get("data") or {}).get("selectedQuantity"),
        (b.get("data") or {}).get("selectedAmount")))
    for it in items:
        say("    cart_item id=%s sku=%s x%s selected=%s invalid=%s" % (
            it.get("id"), it.get("skuId"), it.get("quantity"), it.get("selected"), it.get("invalid")))

    target = cart_item_for(TARGET_SKU)
    if target is None:
        # ★ 自己把商品放进购物车 —— 上一次跑完订单会把这一行吃掉，
        #   不补这一步脚本就只能跑一次。可重复执行是 E2E 脚本的硬要求。
        say("  sku%d not in cart -> POST /api/cart {skuId:%d, quantity:1}" % (TARGET_SKU, TARGET_SKU))
        st, b, _ = japi("POST", "/api/cart", token=demo,
                        body={"skuId": TARGET_SKU, "quantity": 1})
        say("    http=%s code=%s data=%s" % (st, b.get("code"), b.get("data")))
        target = cart_item_for(TARGET_SKU)
    if target is None:
        say("\nABORT: sku%d still not in cart" % TARGET_SKU)
        flush()
        return 1
    item_id = target["id"]

    say("\n[4] PUT /api/cart/%s/selected {selected:true}" % item_id)
    st, b, _ = japi("PUT", "/api/cart/%s/selected" % item_id, token=demo, body={"selected": True})
    say("  http=%s code=%s msg=%s" % (st, b.get("code"), b.get("message")))
    chk("cart item selected", st == 200 and b.get("code") == 200)

    say("\n[5] GET /api/cart  (settlement preview)")
    st, b, _ = japi("GET", "/api/cart", token=demo)
    d = b.get("data") or {}
    say("  http=%s selectedQuantity=%s selectedAmount=%s" % (
        st, d.get("selectedQuantity"), d.get("selectedAmount")))
    chk("settlement preview = 1 x %s" % target.get("price"),
        d.get("selectedQuantity") == 1 and str(d.get("selectedAmount")) == str(target.get("price")))

    # ---------------------------------------------------------- [6] order
    say("\n[6] POST /api/orders {addressId:%d}" % ADDRESS_ID)
    st, b, _ = japi("POST", "/api/orders", token=demo, body={"addressId": ADDRESS_ID})
    order_id = b.get("data") if st == 200 else None
    say("  http=%s code=%s msg=%s newOrderId=%s" % (st, b.get("code"), b.get("message"), order_id))
    chk("order created", st == 200 and isinstance(order_id, int))
    if not isinstance(order_id, int):
        say("\nABORT: no order id -> %s" % short(json.dumps(b, ensure_ascii=False)))
        flush()
        return 1
    chk("new order id is fresh (> %d)" % max_order_id, order_id > max_order_id)

    say("\n[7] GET /api/orders/%d  (must be PENDING_PAYMENT, paidAt NULL)" % order_id)
    st, b, _ = japi("GET", "/api/orders/%s" % order_id, token=demo)
    od = b.get("data") or {}
    say("  http=%s code=%s status=%s payAmount=%s paidAt=%s items=%d" % (
        st, b.get("code"), od.get("status"), od.get("payAmount"), od.get("paidAt"),
        len(od.get("items") or [])))
    for it in (od.get("items") or []):
        say("    item sku=%s %s x%s @ %s" % (it.get("skuId"), it.get("skuName"),
                                             it.get("quantity"), it.get("price")))
    order_pay_amount = str(od.get("payAmount"))
    chk("order is PENDING_PAYMENT", od.get("status") == "PENDING_PAYMENT")
    chk("paidAt still NULL", od.get("paidAt") is None)

    say("\n[8] BASELINE AFTER ORDER -- the lock happens HERE, not at payment")
    mid_inv4 = inv(TARGET_SKU)
    say(inv_line("after order", TARGET_SKU, mid_inv4))
    say("  delta: available %+d  locked %+d  sold %+d" % (
        mid_inv4["available"] - base_inv4["available"],
        mid_inv4["locked"] - base_inv4["locked"],
        mid_inv4["sold"] - base_inv4["sold"]))
    chk("order LOCKED the stock: available -1, locked +1, sold +0",
        mid_inv4["available"] == base_inv4["available"] - 1
        and mid_inv4["locked"] == base_inv4["locked"] + 1
        and mid_inv4["sold"] == base_inv4["sold"])

    say("\n[8b] GET /api/cart -- selected rows are consumed by the order")
    st, b, _ = japi("GET", "/api/cart", token=demo)
    left = (b.get("data") or {}).get("items") or []
    say("  http=%s items_left=%d" % (st, len(left)))
    chk("cart cleared of the selected row", len(left) == 0)

    # ---------------------------------------------------------- [9] pay
    say("\n[9] POST /api/payments {orderId:%d, method:ALIPAY}  (no amount field exists)" % order_id)
    st, b, _ = japi("POST", "/api/payments", token=demo,
                    body={"orderId": order_id, "method": "ALIPAY"})
    pd = b.get("data") or {}
    say("  http=%s code=%s msg=%s" % (st, b.get("code"), b.get("message")))
    say("  data: id=%s paymentNo=%s orderNo=%s amount=%s method=%s status=%s paidAt=%s" % (
        pd.get("id"), pd.get("paymentNo"), pd.get("orderNo"), pd.get("amount"),
        pd.get("method"), pd.get("status"), pd.get("paidAt")))
    pay_id = pd.get("id")
    chk("payment succeeded", st == 200 and b.get("code") == 200 and pd.get("status") == "SUCCESS")
    chk("amount == order.payAmount (%s)" % order_pay_amount, str(pd.get("amount")) == order_pay_amount)
    chk("orderNo is populated (JOIN / snapshot works)", bool(pd.get("orderNo")))

    say("\n[10] GET /api/orders/%d  (must now be PAID)" % order_id)
    st, b, _ = japi("GET", "/api/orders/%s" % order_id, token=demo)
    od2 = b.get("data") or {}
    say("  http=%s status=%s paidAt=%s" % (st, od2.get("status"), od2.get("paidAt")))
    chk("order flipped to PAID", od2.get("status") == "PAID")
    chk("paidAt written", od2.get("paidAt") is not None)

    say("\n[11] GET /api/payments  (owner sees it, newest first)")
    st, b, _ = japi("GET", "/api/payments", token=demo)
    d = b.get("data") or {}
    recs = d.get("records") or []
    say("  http=%s total=%s size=%s records=%d" % (st, d.get("total"), d.get("size"), len(recs)))
    for r in recs:
        say("    id=%s order=%s amount=%s method=%s status=%s" % (
            r.get("id"), r.get("orderId"), r.get("amount"), r.get("method"), r.get("status")))
    chk("new payment is visible", recs and recs[0].get("id") == pay_id)

    say("\n[11b] GET /api/payments/%s  (detail)" % pay_id)
    st, b, _ = japi("GET", "/api/payments/%s" % pay_id, token=demo)
    say("  http=%s code=%s id=%s orderNo=%s" % (st, b.get("code"),
                                                (b.get("data") or {}).get("id"),
                                                (b.get("data") or {}).get("orderNo")))
    chk("detail returns the same row", (b.get("data") or {}).get("id") == pay_id)

    # ---------------------------------------------------------- [12] stock
    say("\n[12] FINAL STOCK -- payment moves locked -> sold, available untouched")
    end_inv4 = inv(TARGET_SKU)
    say(inv_line("after payment", TARGET_SKU, end_inv4))
    say("  delta: available %+d  locked %+d  sold %+d" % (
        end_inv4["available"] - mid_inv4["available"],
        end_inv4["locked"] - mid_inv4["locked"],
        end_inv4["sold"] - mid_inv4["sold"]))
    say("  vs baseline: available %+d  locked %+d  sold %+d" % (
        end_inv4["available"] - base_inv4["available"],
        end_inv4["locked"] - base_inv4["locked"],
        end_inv4["sold"] - base_inv4["sold"]))
    chk("payment: locked -1, sold +1, available UNCHANGED",
        end_inv4["locked"] == mid_inv4["locked"] - 1
        and end_inv4["sold"] == mid_inv4["sold"] + 1
        and end_inv4["available"] == mid_inv4["available"])
    chk("identity total=avail+locked+sold still holds", end_inv4["id_ok"])
    chk("one order -> exactly one payment row", pay_rows(order_id) == 1)

    # ---------------------------------------------------------- [13] repeat
    say("\n[13] DUPLICATE PAY -- same orderId again")
    seq_a = pay_seq()
    st, b, _ = japi("POST", "/api/payments", token=demo,
                    body={"orderId": order_id, "method": "WECHAT"})
    seq_b = pay_seq()
    say("  http=%s code=%s msg=%s data=%s" % (
        st, b.get("code"), b.get("message"),
        short(json.dumps(b.get("data"), ensure_ascii=False))))
    say("  payments rows for order=%d" % pay_rows(order_id))
    say("  payments_seq %d -> %d (consumed %d) while rows stayed the same" % (
        seq_a, seq_b, seq_b - seq_a))
    chk("duplicate rejected: HTTP 200 + code 400", st == 200 and b.get("code") == 400)
    chk("still exactly one payment row", pay_rows(order_id) == 1)
    chk("transaction rolled back (seq burned an id, row vanished)", seq_b - seq_a == 1)
    chk("stock untouched by the rolled-back attempt",
        inv(TARGET_SKU) == end_inv4)

    # ---------------------------------------------------------- [14] IDOR
    say("\n[14] IDOR (intruder id=2 has NO orders and NO payments)")
    say("  ⚠️ 口径提醒：业务异常走 GlobalExceptionHandler.handleBusinessException，")
    say("     它返回 Result<Void>（无 @ResponseStatus）⇒ 【HTTP 200 + body.code=404】，")
    say("     而不是 HTTP 404。真实 HTTP 状态码只出现在 Security 层的 401/403。")

    def body_code(raw):
        try:
            return json.loads(raw).get("code")
        except ValueError:
            return None

    st_o, raw_o_foreign = api("GET", "/api/orders/%s" % order_id, token=intr)
    st_o2, raw_o_absent = api("GET", "/api/orders/99999999", token=intr)
    say("  GET /api/orders/%s        -> http=%s code=%s %s" % (
        order_id, st_o, body_code(raw_o_foreign), short(raw_o_foreign, 120)))
    say("  GET /api/orders/99999999  -> http=%s code=%s %s" % (
        st_o2, body_code(raw_o_absent), short(raw_o_absent, 120)))
    chk("intruder gets business-404 for demo's order",
        st_o == 200 and body_code(raw_o_foreign) == 404)
    chk("foreign-404 == absent-404 (byte identical, order)",
        raw_o_foreign.strip() == raw_o_absent.strip())

    st_p, raw_p_foreign = api("GET", "/api/payments/%s" % pay_id, token=intr)
    st_p2, raw_p_absent = api("GET", "/api/payments/99999999", token=intr)
    say("  GET /api/payments/%s        -> http=%s code=%s %s" % (
        pay_id, st_p, body_code(raw_p_foreign), short(raw_p_foreign, 120)))
    say("  GET /api/payments/99999999  -> http=%s code=%s %s" % (
        st_p2, body_code(raw_p_absent), short(raw_p_absent, 120)))
    chk("intruder gets business-404 for demo's payment",
        st_p == 200 and body_code(raw_p_foreign) == 404)
    chk("foreign-404 == absent-404 (byte identical, payment)",
        raw_p_foreign.strip() == raw_p_absent.strip())

    # ---- 对照：同一个 URL，匿名访问拿到的是【真 HTTP 401】（过滤器写的响应）。
    #      两边并排放，才看得出「200 不是万能的」。
    st_anon, raw_anon = api("GET", "/api/orders/%s" % order_id)
    say("  [contrast] anonymous 同一 URL -> http=%s %s" % (st_anon, short(raw_anon, 120)))
    chk("contrast: anonymous gets a REAL HTTP 401 on the same URL", st_anon == 401)

    st_l, b_l, _ = japi("GET", "/api/payments", token=intr)
    say("  intruder GET /api/payments -> total=%s records=%d" % (
        (b_l.get("data") or {}).get("total"), len((b_l.get("data") or {}).get("records") or [])))
    chk("intruder list is empty", (b_l.get("data") or {}).get("total") == 0)

    # ---------------------------------------------------------- [15] leftover
    say("\n[15] DAY-12 LEFTOVER order #%d (PENDING_PAYMENT, sku5 x3) -- pay it off" % LEFTOVER_ORDER)
    st, b, _ = japi("GET", "/api/orders/%d" % LEFTOVER_ORDER, token=demo)
    lo = b.get("data") or {}
    say("  before: status=%s payAmount=%s" % (lo.get("status"), lo.get("payAmount")))
    if lo.get("status") == "PENDING_PAYMENT":
        st, b, _ = japi("POST", "/api/payments", token=demo,
                        body={"orderId": LEFTOVER_ORDER, "method": "WECHAT"})
        lpd = b.get("data") or {}
        say("  pay   : http=%s code=%s paymentNo=%s amount=%s" % (
            st, b.get("code"), lpd.get("paymentNo"), lpd.get("amount")))
        st, b, _ = japi("GET", "/api/orders/%d" % LEFTOVER_ORDER, token=demo)
        say("  after : status=%s paidAt=%s" % ((b.get("data") or {}).get("status"),
                                                (b.get("data") or {}).get("paidAt")))
        end_inv5 = inv(5)
        say(inv_line("sku5 before", 5, base_inv5))
        say(inv_line("sku5 after", 5, end_inv5))
        say("  delta: available %+d  locked %+d  sold %+d" % (
            end_inv5["available"] - base_inv5["available"],
            end_inv5["locked"] - base_inv5["locked"],
            end_inv5["sold"] - base_inv5["sold"]))
        chk("leftover #%d now PAID" % LEFTOVER_ORDER, (b.get("data") or {}).get("status") == "PAID")
        chk("sku5 locked 3 -> 0, sold 0 -> 3, available unchanged",
            end_inv5["locked"] == 0 and end_inv5["sold"] == 3
            and end_inv5["available"] == base_inv5["available"])
        chk("sku5 identity holds", end_inv5["id_ok"])
        chk("leftover order has exactly one payment row", pay_rows(LEFTOVER_ORDER) == 1)
    else:
        say("  (already %s -- skipped)" % lo.get("status"))

    # ---------------------------------------------------------- [16] audit
    say("\n[16] FINAL DATABASE AUDIT (psql)")
    fin_orders = int(one("SELECT count(*) FROM orders"))
    fin_pays = int(one("SELECT count(*) FROM payments"))
    dupes = one("SELECT coalesce(string_agg(order_id::text||' x'||c, ', '), '-') FROM "
                "(SELECT order_id, count(*) c FROM payments GROUP BY order_id HAVING count(*) > 1) t")
    pending = one("SELECT coalesce(string_agg(id::text, ','), '-') FROM orders WHERE status='PENDING_PAYMENT'")
    neg = one("SELECT coalesce(string_agg(sku_id::text, ','), '-') FROM inventories "
              "WHERE available_stock < 0 OR locked_stock < 0 OR sold_stock < 0")
    bad_identity = one("SELECT coalesce(string_agg(sku_id::text, ','), '-') FROM inventories "
                       "WHERE total_stock <> available_stock + locked_stock + sold_stock")
    say("  orders %d -> %d   payments %d -> %d" % (base_orders, fin_orders, base_pays, fin_pays))
    say("  orders still PENDING_PAYMENT : %s" % pending)
    say("  payments with >1 row per order : %s" % dupes)
    say("  negative stock                 : %s" % neg)
    say("  broken identity (total<>a+l+s) : %s" % bad_identity)
    say("  all 7 inventories:")
    for s in range(1, 8):
        say(inv_line("", s, inv(s)))
    chk("no order was paid twice", dupes == "-")
    chk("no negative stock anywhere", neg == "-")
    chk("identity holds for ALL 7 SKUs", bad_identity == "-")

    # ---------------------------------------------------------- verdict
    say("\n" + "=" * 78)
    say("ASSERTIONS")
    say("=" * 78)
    passed = 0
    for name, good in checks:
        say("  [%s] %s" % ("PASS" if good else "FAIL", name))
        passed += 1 if good else 0
    say("\nRESULT: %d/%d passed" % (passed, len(checks)))
    say("VERDICT: %s" % ("END-TO-END OK -- cart -> order -> payment -> PAID, stock reconciled,"
                         " IDOR hidden, duplicate payment rejected"
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
