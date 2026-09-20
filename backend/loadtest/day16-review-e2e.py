# -*- coding: utf-8 -*-
"""
Day 16 -- product reviews: the last link of milestone M1.

Where this fits
---------------
Day 12 placed the order, Day 13 paid it, Day 14 added the backward edge
(cancel / timeout), Day 15 walked the forward edges (PAID -> SHIPPED ->
COMPLETED). Day 16 attaches a REVIEW to a completed purchase -- and with that,
M1 ("place -> pay -> receive -> review") is closed.

Why this day is different from Day 13/14/15
-------------------------------------------
Every earlier day wrote into tables that ALREADY had teeth: `payments` had FKs,
`orders.status` was guarded by CAS WHERE clauses. `reviews` did not. It shipped
on Day 03 with its FKs but with ZERO unique constraints, and its
`order_item_id` column was NULLABLE.

★★ That second detail is the trap. PostgreSQL's UNIQUE constraint EXEMPTS NULL:
two rows whose order_item_id is NULL are "not equal" to each other and are BOTH
legal. So adding UNIQUE alone leaves "one review per order line" unenforced --
and worse, `INSERT ... ON CONFLICT (order_item_id) DO NOTHING` gets bypassed by
NULL rows too. Both gaps are proven in `day16-probe.sql` (PROBE 5) and closed by
`../sql/04-review-constraints.sql`.

The headline assertion: server-side derivation
----------------------------------------------
`POST /api/reviews` takes exactly ONE identifier from the client: `orderItemId`.
`user_id` comes from the token; `order_id` and `product_id` are looked up from
`order_items`. Section [9] asserts that forging those fields in the request body
changes nothing -- because if `product_id` were client-supplied, anyone holding
one legitimate completed order could mint five-star reviews for ANY product on
the platform.

The second headline: ON CONFLICT is a CAS
-----------------------------------------
The duplicate-review defence is `INSERT ... ON CONFLICT (order_item_id) DO
NOTHING`, whose ROW COUNT is the answer: 1 = inserted, 0 = already reviewed.
That is structurally identical to `UPDATE ... WHERE status = '...'` -- hand the
decision to the database and read the affected-row count. Section [5] proves it
is atomic by firing 8 concurrent requests at one order line: exactly one wins.

Everything is asserted against the DATABASE, not against the API's own claims.
Sections [3]/[11] re-derive every important value from psql.

Re-runnable and self-cleaning
-----------------------------
It snapshots the baseline, reasons only about rows it created, cleans up in a
`finally`, and re-verifies the baseline byte-for-byte at the end.

Usage:
    python day16-review-e2e.py
Report (utf-8) is written next to this file: day16-review-e2e-report.txt
"""
import http.client
import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080"
DOCKER = r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
ADDRESS_ID = 2          # demo's default address
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "day16-review-e2e-report.txt")

# One order, three lines -> three independent order_item_ids, one job each:
#   A = happy-path review, then the duplicate attempt
#   B = the concurrency shoot-out (8 threads, exactly one winner)
#   C = IDOR probe / parameter validation / forged-field attempt
SKU_A, SKU_B, SKU_C = 3, 4, 5
CART_SKUS = [SKU_A, SKU_B, SKU_C]
BOGUS_ITEM = 999999     # an order_item_id that does not exist

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
    """★ Day 13 教训：业务错误码藏在 body.code 里（HTTP 仍是 200）。
    GlobalExceptionHandler 的方法没有 @ResponseStatus，真实 HTTP 状态码
    只出现在 Security 层写的响应里。"""
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


def status_of(order_id):
    return one("SELECT status FROM orders WHERE id=%d" % order_id) or "(missing)"


def row_counts():
    return one("SELECT (SELECT count(*) FROM orders)||'/'||"
               "(SELECT count(*) FROM payments)||'/'||"
               "(SELECT count(*) FROM order_items)||'/'||"
               "(SELECT count(*) FROM inventory_logs)||'/'||"
               "(SELECT count(*) FROM reviews)")


def review_row(order_item_id):
    """-> dict or None. Proves the three derived columns really came from the DB."""
    out = one("SELECT id||'|'||user_id||'|'||order_id||'|'||product_id||'|'||"
              "rating||'|'||coalesce(content,'')||'|'||status"
              " FROM reviews WHERE order_item_id=%d" % order_item_id)
    if not out:
        return None
    p = [x.strip() for x in out.split("|")]
    if len(p) != 7:
        return None
    return dict(id=int(p[0]), user_id=int(p[1]), order_id=int(p[2]), product_id=int(p[3]),
                rating=int(p[4]), content=p[5], status=int(p[6]))


def review_count():
    return int(one("SELECT count(*) FROM reviews"))


def order_items_of(order_id):
    """-> [(order_item_id, product_id, sku_id), ...] straight from the DB.
    ★ 不依赖订单详情的 JSON 结构 —— 验收脚本自己找靶子。"""
    out = one("SELECT id||'|'||product_id||'|'||sku_id FROM order_items"
              " WHERE order_id=%d ORDER BY id" % order_id)
    rows = []
    for line in out.splitlines():
        p = [x.strip() for x in line.split("|")]
        if len(p) == 3:
            rows.append((int(p[0]), int(p[1]), int(p[2])))
    return rows


def short(raw, n=150):
    raw = raw.replace("\r", "").replace("\n", " ").strip()
    return raw if len(raw) <= n else raw[:n] + " ...(truncated)"


def drift(query):
    return one(query).strip()


# ★ 库存口径：Day 15 已升级为「已售出去的三个状态」。本日【不改口径】，只复核它没被搞坏。
SOLD_DRIFT = """
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

# ★★ 本日新增：评价域守恒式 —— 对账第一次跨出库存域
NO_EVIDENCE = """
    SELECT count(*) FROM reviews r
     LEFT JOIN order_items oi ON oi.id = r.order_item_id
     WHERE oi.id IS NULL OR oi.order_id <> r.order_id OR oi.product_id <> r.product_id
"""
DUP_REVIEW = """
    SELECT count(*) FROM (SELECT order_item_id FROM reviews
                           GROUP BY order_item_id HAVING count(*) > 1) t
"""
REVIEWS_LE_ITEMS = """
    SELECT (SELECT count(*) FROM reviews) <=
           (SELECT count(*) FROM order_items oi JOIN orders o ON o.id = oi.order_id
             WHERE o.status = 'COMPLETED')
"""
REVIEWS_ONLY_ON_COMPLETED = """
    SELECT count(*) FROM reviews r JOIN orders o ON o.id = r.order_id
     WHERE o.status <> 'COMPLETED'
"""


class _Abort(Exception):
    """Early abort that still runs the cleanup in `finally` and still writes the
    report. (A bare `return` would skip the summary + flush.)"""


def concurrent_review(order_item_id, token, n=8):
    """Fire n simultaneous POST /api/reviews at ONE order_item_id.

    ★ Day 12 教训：`urllib.request.urlopen()` 每次新开一条 TCP，
      「同时启动」的线程实际到达间隔可达 ~165ms —— 会把竞态窗口冲散。
      这里用 http.client 直连 + Barrier 前先建连，让 8 个请求真正挤在一起。
      （http.client 直连 127.0.0.1，天然不过系统代理。）
    """
    barrier = threading.Barrier(n)
    results = [None] * n

    def worker(i):
        conn = http.client.HTTPConnection("127.0.0.1", 8080, timeout=30)
        try:
            conn.request("GET", "/api/hello")          # 预热：先握手，再等闸门
            conn.getresponse().read()
        except Exception:                                            # noqa: BLE001
            pass
        payload = json.dumps({"orderItemId": order_item_id,
                              "rating": 5,
                              "content": "concurrent-%d" % i})
        barrier.wait()
        try:
            conn.request("POST", "/api/reviews", body=payload,
                         headers={"Content-Type": "application/json",
                                  "Authorization": "Bearer " + token})
            r = conn.getresponse()
            results[i] = (r.status, r.read().decode("utf-8", "replace"))
        except Exception as e:                                       # noqa: BLE001
            results[i] = (-1, repr(e))
        finally:
            conn.close()

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return results


# ================================================================ main
def main():
    checks = []

    def chk(name, good):
        checks.append((name, bool(good)))

    say("=" * 78)
    say("Day 16 -- product reviews: closing milestone M1")
    say("target : %s   accounts: demo(id=1) / admin(id=1) / intruder(id=2)" % BASE)
    say("skus under test: %s" % CART_SKUS)
    say("=" * 78)

    # ---------------------------------------------------------- [0] baseline
    say("\n[0] BASELINE FINGERPRINT")
    base_all = all_inv()
    high_water = int(one("SELECT coalesce(max(id),0) FROM inventory_logs"))
    base_counts = row_counts()
    base_reviews = review_count()
    for sku in sorted(base_all):
        say(inv_line("baseline", sku, base_all[sku]))
    say("  rows orders/payments/order_items/inventory_logs/reviews = %s" % base_counts)
    chk("every SKU satisfies total = available + locked + sold",
        all(r["total"] == r["available"] + r["locked"] + r["sold"] for r in base_all.values()))
    chk("baseline sold conservation holds (Day 15 rule: PAID+SHIPPED+COMPLETED)",
        drift(SOLD_DRIFT) == "0")
    chk("baseline locked conservation holds", drift(LOCKED_DRIFT) == "0")
    say("  ★ reviews at start = %d   (Day 03 built the table; Day 16 is its first use)"
        % base_reviews)

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
    chk("admin login succeeded (needed to ship the target order)", bool(admin))

    st, b, _ = japi("POST", "/api/auth/login", body={"username": "intruder", "password": "intruder"})
    intruder = (b.get("data") or {}).get("token")
    say("  intruder  http=%s code=%s userId=%s token_len=%d"
        % (st, b.get("code"), (b.get("data") or {}).get("userId"), len(intruder or "")))
    chk("intruder login succeeded", bool(intruder))

    if not demo or not admin or not intruder:
        say("\nABORT: need all three tokens")
        flush()
        return 1

    # ---------------------------------------------------------------- helpers
    def cart_items():
        return (japi("GET", "/api/cart", token=demo)[1].get("data") or {}).get("items") or []

    def place_order(skus, qty=1):
        """Deselect everything, put exactly `skus` in the cart (selected), then order."""
        for it in cart_items():
            if it.get("selected"):
                japi("PUT", "/api/cart/%s/selected" % it["id"], token=demo,
                     body={"selected": False})
        for sku in skus:
            found = next((x for x in cart_items() if x.get("skuId") == sku), None)
            if found is None:
                japi("POST", "/api/cart", token=demo, body={"skuId": sku, "quantity": qty})
                found = next((x for x in cart_items() if x.get("skuId") == sku), None)
            if found is None:
                return None, "cart-add-failed"
            japi("PUT", "/api/cart/%s" % found["id"], token=demo, body={"quantity": qty})
            japi("PUT", "/api/cart/%s/selected" % found["id"], token=demo,
                 body={"selected": True})
        st_, b_, raw_ = japi("POST", "/api/orders", token=demo, body={"addressId": ADDRESS_ID})
        oid = b_.get("data") if st_ == 200 and isinstance(b_.get("data"), int) else None
        return oid, b_.get("code")

    def pay(order_id):
        return japi("POST", "/api/payments", token=demo,
                    body={"orderId": order_id, "method": "ALIPAY"})

    def ship(order_id):
        return japi("POST", "/api/orders/%d/ship" % order_id, token=admin)

    def confirm(order_id):
        return japi("POST", "/api/orders/%d/confirm" % order_id, token=demo)

    def submit_review(order_item_id, rating=5, content="solid.", token=None, extra=None):
        body = {"orderItemId": order_item_id, "rating": rating, "content": content}
        if extra:
            body.update(extra)
        return japi("POST", "/api/reviews", token=token or demo, body=body)

    created = []
    touched = set()

    try:
        # ============================================ [2] build the target order
        say("\n" + "-" * 78)
        say("ORDER A -- one order, three lines: the review target for the whole run")
        say("-" * 78)
        say("\n[2] place A -> pay -> ship(admin) -> confirm(demo) -> COMPLETED")
        order_a, code_a = place_order(CART_SKUS)
        say("  POST /api/orders (skus %s) -> order=%s code=%s" % (CART_SKUS, order_a, code_a))
        chk("order A created", isinstance(order_a, int))
        if not isinstance(order_a, int):
            say("\nABORT: could not create order A")
            raise _Abort()
        created.append(order_a)
        touched |= set(CART_SKUS)
        a_placed = {s: inv(s) for s in CART_SKUS}

        st_p, b_p, _ = pay(order_a)
        say("  POST /api/payments -> http=%s code=%s" % (st_p, b_p.get("code")))
        chk("order A paid", st_p == 200 and b_p.get("code") == 200 and status_of(order_a) == "PAID")

        st_s, b_s, raw_s = ship(order_a)
        say("  POST /api/orders/%d/ship (admin) -> http=%s code=%s" % (order_a, st_s, b_s.get("code")))
        chk("order A shipped", status_of(order_a) == "SHIPPED")

        st_c, b_c, raw_c = confirm(order_a)
        say("  POST /api/orders/%d/confirm (demo) -> http=%s code=%s" % (order_a, st_c, b_c.get("code")))
        chk("★★ order A reached COMPLETED -- the M1 precondition for a review",
            status_of(order_a) == "COMPLETED")

        items_a = order_items_of(order_a)
        by_sku = {sku: (iid, pid) for (iid, pid, sku) in items_a}
        say("  order_items: %s" % [(i, p, s) for (i, p, s) in items_a])
        chk("order A has one line per cart SKU", set(by_sku) == set(CART_SKUS))
        if set(by_sku) != set(CART_SKUS):
            say("\nABORT: unexpected order lines")
            raise _Abort()
        item_a, pid_a = by_sku[SKU_A]
        item_b, pid_b = by_sku[SKU_B]
        item_c, pid_c = by_sku[SKU_C]
        say("  review targets: item_a=%d (sku%d)  item_b=%d (sku%d)  item_c=%d (sku%d)"
            % (item_a, SKU_A, item_b, SKU_B, item_c, SKU_C))

        # ============================================ [3] the review itself
        say("\n" + "-" * 78)
        say("[3] POST /api/reviews -- ★★ the three derived columns must come from the DB")
        say("-" * 78)
        st_r, b_r, raw_r = submit_review(item_a, rating=5, content="hello from day16")
        say("  POST /api/reviews {orderItemId:%d, rating:5} -> http=%s code=%s %s"
            % (item_a, st_r, b_r.get("code"), short(raw_r, 110)))
        chk("review accepted (code 200)", st_r == 200 and b_r.get("code") == 200)

        rv = review_row(item_a)
        say("  db row: %s" % rv)
        chk("exactly one review row for this order line", rv is not None)
        if rv:
            oi_order = int(one("SELECT order_id FROM order_items WHERE id=%d" % item_a))
            oi_user = int(one("SELECT user_id FROM orders WHERE id=%d" % order_a))
            say("  evidence: order_items says order_id=%d product_id=%d; orders says user_id=%d"
                % (oi_order, pid_a, oi_user))
            chk("★★ user_id came from the TOKEN, not the client", rv["user_id"] == oi_user)
            chk("★★ order_id was DERIVED from order_items", rv["order_id"] == oi_order)
            chk("★★ product_id was DERIVED from order_items (the anti-fraud rule)",
                rv["product_id"] == pid_a)
            chk("rating persisted as 5", rv["rating"] == 5)
            chk("content persisted", rv["content"] == "hello from day16")
            chk("status defaults to 1 (visible)", rv["status"] == 1)

        # ============================================ [4] duplicate
        say("\n[4] the same order line again -- ON CONFLICT DO NOTHING must answer 0 rows")
        st_dup, b_dup, raw_dup = submit_review(item_a, rating=1, content="second attempt")
        say("  POST /api/reviews (same orderItemId) -> http=%s code=%s %s"
            % (st_dup, b_dup.get("code"), short(raw_dup, 110)))
        chk("★ duplicate review refused with code=400 (a normal outcome, not a 500)",
            b_dup.get("code") == 400)
        chk("★ the DB still holds exactly ONE row for that order line",
            int(one("SELECT count(*) FROM reviews WHERE order_item_id=%d" % item_a)) == 1)
        rv2 = review_row(item_a)
        chk("★ the first review was NOT overwritten (rating still 5)",
            rv2 is not None and rv2["rating"] == 5)

        # ============================================ [5] concurrency
        say("\n" + "-" * 78)
        say("[5] ★★ 8 threads, ONE order line -- exactly one winner (the constraint has teeth)")
        say("-" * 78)
        results = concurrent_review(item_b, demo, n=8)
        ok = sum(1 for st_, raw_ in results if body_code(raw_) == 200)
        bad = sum(1 for st_, raw_ in results if body_code(raw_) == 400)
        other = [(st_, short(raw_, 70)) for st_, raw_ in results
                 if body_code(raw_) not in (200, 400)]
        say("  200 -> %d  400 -> %d  other -> %d" % (ok, bad, len(other)))
        for st_, raw_ in results:
            say("    http=%-4s code=%-5s %s" % (st_, body_code(raw_), short(raw_, 70)))
        chk("★★ EXACTLY ONE of the 8 concurrent requests won", ok == 1)
        chk("★★ the other 7 were refused with code=400", bad == 7)
        chk("no request blew up (no 500 / transport error)", not other)
        chk("★★ the database holds EXACTLY ONE review for that order line",
            int(one("SELECT count(*) FROM reviews WHERE order_item_id=%d" % item_b)) == 1)

        # ============================================ [6] IDOR
        say("\n" + "-" * 78)
        say("[6] IDOR -- reviewing somebody else's purchase must be invisible")
        say("-" * 78)
        st_i, raw_i = api("POST", "/api/reviews", token=intruder,
                          body={"orderItemId": item_c, "rating": 5, "content": "not mine"})
        say("  intruder -> demo's item %d : http=%s code=%s %s"
            % (item_c, st_i, body_code(raw_i), short(raw_i, 100)))
        chk("★ intruder gets a business-404 (indistinguishable from 'not found')",
            body_code(raw_i) == 404)

        st_m, raw_m = api("POST", "/api/reviews", token=demo,
                          body={"orderItemId": BOGUS_ITEM, "rating": 5, "content": "ghost"})
        say("  demo -> a non-existent item  : http=%s code=%s %s"
            % (st_m, body_code(raw_m), short(raw_m, 100)))
        chk("★ a non-existent order line gives the same business-404",
            body_code(raw_m) == 404)
        chk("★★ the two 404 bodies are BYTE-IDENTICAL (the mask has no seam)",
            raw_i.strip() == raw_m.strip())
        chk("★ nothing was written by either attempt",
            int(one("SELECT count(*) FROM reviews WHERE order_item_id=%d" % item_c)) == 0)

        # ============================================ [7] eligibility
        say("\n" + "-" * 78)
        say("[7] eligibility -- only COMPLETED orders may be reviewed")
        say("-" * 78)
        order_b, code_b = place_order([SKU_A])
        say("  ORDER B placed -> %s" % order_b)
        chk("order B created", isinstance(order_b, int))
        if not isinstance(order_b, int):
            say("\nABORT: could not create order B")
            raise _Abort()
        created.append(order_b)
        items_b = order_items_of(order_b)
        item_elig = items_b[0][0]

        st_e1, b_e1, raw_e1 = submit_review(item_elig)
        say("  review a PENDING_PAYMENT order's line -> code=%s %s"
            % (b_e1.get("code"), short(raw_e1, 90)))
        chk("★ cannot review before payment (code=400)", b_e1.get("code") == 400)
        chk("order B still PENDING_PAYMENT", status_of(order_b) == "PENDING_PAYMENT")

        st_pb, b_pb, _ = pay(order_b)
        say("  pay order B -> code=%s" % b_pb.get("code"))
        chk("order B paid", status_of(order_b) == "PAID")
        st_e2, b_e2, raw_e2 = submit_review(item_elig)
        say("  review a PAID order's line -> code=%s %s"
            % (b_e2.get("code"), short(raw_e2, 90)))
        chk("★ cannot review while only PAID (code=400)", b_e2.get("code") == 400)

        st_sb, b_sb, _ = ship(order_b)
        say("  ship order B -> code=%s" % b_sb.get("code"))
        chk("order B shipped", status_of(order_b) == "SHIPPED")
        st_e3, b_e3, raw_e3 = submit_review(item_elig)
        say("  review a SHIPPED order's line -> code=%s %s"
            % (b_e3.get("code"), short(raw_e3, 90)))
        chk("★★ cannot review a merely SHIPPED order -- COMPLETED is required (code=400)",
            b_e3.get("code") == 400)
        chk("★ three eligibility refusals wrote nothing",
            int(one("SELECT count(*) FROM reviews WHERE order_item_id=%d" % item_elig)) == 0)

        # ============================================ [8] validation
        say("\n" + "-" * 78)
        say("[8] parameter validation (this runs BEFORE any DB lookup)")
        say("-" * 78)
        for label, payload in [
                ("rating = 0   ", {"rating": 0}),
                ("rating = 6   ", {"rating": 6}),
                ("rating = null", {"rating": None}),
                ("content 501ch", {"content": "测" * 501}),
        ]:
            st_v, b_v, raw_v = submit_review(BOGUS_ITEM, rating=5, content="ok", extra=payload)
            say("  %s -> code=%s %s" % (label, b_v.get("code"), short(raw_v, 90)))
            chk("★ %s refused with code=400" % label.strip(), b_v.get("code") == 400)
        say("  ★ 说明：rating 必须声明成【包装类型 Integer】+ @NotNull。")
        say("    写成基本类型 int 时，rating=null 会在 Jackson 反序列化阶段就抛")
        say("    HttpMessageNotReadableException —— 而 GlobalExceptionHandler 还没接它，")
        say("    结果是 code=500（本组会当场抓出来）。")

        # ============================================ [9] forged fields
        say("\n" + "-" * 78)
        say("[9] ★★ forged fields -- the client cannot vote on somebody else's product")
        say("-" * 78)
        st_f, b_f, raw_f = submit_review(
            item_c, rating=4, content="forged attempt",
            extra={"userId": 999999, "orderId": 999999, "productId": 999999})
        say("  POST with userId/orderId/productId = 999999 -> http=%s code=%s"
            % (st_f, b_f.get("code")))
        chk("the review is accepted (unknown fields are simply ignored)", b_f.get("code") == 200)
        rv_f = review_row(item_c)
        say("  db row: %s   (evidence: real order=%d product=%d user=%d)"
            % (rv_f, order_a, pid_c, int(one("SELECT user_id FROM orders WHERE id=%d" % order_a))))
        chk("★★ product_id forged as 999999 did NOT land in the DB",
            rv_f is not None and rv_f["product_id"] == pid_c)
        chk("★★ order_id forged as 999999 did NOT land in the DB",
            rv_f is not None and rv_f["order_id"] == order_a)
        chk("★★ user_id forged as 999999 did NOT land in the DB",
            rv_f is not None
            and rv_f["user_id"] == int(one("SELECT user_id FROM orders WHERE id=%d" % order_a)))

        # ============================================ [10] reading
        say("\n" + "-" * 78)
        say("[10] reading reviews -- per product (PUBLIC) / mine (logged in) / aggregates")
        say("-" * 78)
        st_pub, b_pub, raw_pub = japi("GET", "/api/products/%d/reviews?page=1&size=10" % pid_a)
        say("  GET /api/products/%d/reviews  (NO token) -> http=%s code=%s"
            % (pid_a, st_pub, b_pub.get("code")))
        chk("★★ the product review list is PUBLIC -- a guest (no token) can read it",
            st_pub == 200 and b_pub.get("code") == 200)
        data = b_pub.get("data") or {}
        recs = data.get("records") or []
        say("  total=%s current=%s size=%s reviewCount=%s avgRating=%s"
            % (data.get("total"), data.get("current"), data.get("size"),
               data.get("reviewCount"), data.get("avgRating")))
        chk("the review just written shows up in the list",
            any(x.get("orderItemId") == item_a for x in recs))
        db_cnt = int(one("SELECT count(*) FROM reviews WHERE product_id=%d AND status=1" % pid_a))
        chk("★ aggregate reviewCount equals the database count (%d)" % db_cnt,
            data.get("reviewCount") == db_cnt)
        db_avg = one("SELECT coalesce(round(avg(rating)::numeric,1),0) FROM reviews"
                     " WHERE product_id=%d AND status=1" % pid_a)
        got_avg = data.get("avgRating")
        chk("★ aggregate avgRating equals the database AVG (%s)" % db_avg,
            got_avg is not None and abs(float(got_avg) - float(db_avg)) < 0.001)

        st_my, b_my, _ = japi("GET", "/api/reviews/my?page=1&size=10", token=demo)
        my = (b_my.get("data") or {}).get("records") or []
        my_items = [x.get("orderItemId") for x in my]
        say("  GET /api/reviews/my (demo) -> http=%s code=%s count=%s items=%s"
            % (st_my, b_my.get("code"), len(my), my_items))
        chk("my reviews contain this run's order lines",
            item_a in my_items and item_c in my_items)
        chk("★ every order line this run wrote appears in 'my reviews'",
            all(i in my_items for i in (item_a, item_b, item_c)))
        chk("★ a line that was never reviewed successfully does NOT appear",
            item_elig not in my_items)

        say("\n  pagination edges (Day 12's three traps)")
        for q, note in [("page=1&size=0", "size=0 -> clamped up to 1"),
                        ("page=1&size=-1", "size<0 -> must NOT dump the whole table"),
                        ("page=0&size=10", "page<1 -> MP tolerates it"),
                        ("page=1&size=999", "size>100 -> must be clamped")]:
            st_z, b_z, raw_z = japi("GET", "/api/products/%d/reviews?%s" % (pid_a, q))
            n = len((b_z.get("data") or {}).get("records") or [])
            say("    %-16s code=%-5s records=%d   (%s)" % (q, b_z.get("code"), n, note))
            chk("★ pagination %s does not blow up" % q, b_z.get("code") == 200)
            if "size=0" in q:
                # ★ 本行曾是【脚本自身的假失败】：原断言 n == 0 照搬了 MP 的原生行为
                #   （size=0 -> LIMIT 0 -> 空列表），但规划的夹紧规则是 size < 1 归一到 1
                #   （见 §4.4），两者互斥。实现按夹紧走 ⇒ 这里断言「被夹到 1」。
                #   同 Day 15「断言必须挂在正确的时点上」一类：断言要对着【设计】写，
                #   不是对着【某个库的默认行为】写。
                chk("★★ size=0 was clamped up to 1 (never dumps the table, never a silent empty)",
                    n == 1)
            if "size=-1" in q:
                chk("★★ size=-1 did NOT dump the whole table", n <= 100)
            if "size=999" in q:
                chk("★★ size=999 was clamped to at most 100", n <= 100)

        # ============================================ [11] reconciliation
        say("\n" + "=" * 78)
        say("[11] ★★ RECONCILIATION -- now crossing OUT of the inventory domain")
        say("=" * 78)
        ne = drift(NO_EVIDENCE)
        dp = drift(DUP_REVIEW)
        le = drift(REVIEWS_LE_ITEMS).lower() in ("t", "true")
        oc = drift(REVIEWS_ONLY_ON_COMPLETED)
        say("  (1) reviews with no purchase evidence (LEFT JOIN order_items)   -> %s rows" % ne)
        say("  (2) order lines reviewed more than once                         -> %s rows" % dp)
        say("  (3) count(reviews) <= count(COMPLETED order lines)              -> %s" % le)
        say("  (4) reviews hanging off a non-COMPLETED order                   -> %s rows" % oc)
        chk("★★ every review traces back to a real purchase (0 orphan rows)", ne == "0")
        chk("★★ no order line was reviewed twice", dp == "0")
        chk("★ review count never exceeds completed order lines", le)
        chk("★★ no review exists on a non-COMPLETED order", oc == "0")
        say("  ★ 守恒式 (1) 就是「三重派生真的生效」的证据：若 product_id 由客户端传，这里立刻报漂移。")
        say("  ★ 守恒式 (4) 是资格校验的守恒式：评价只可能出现在 COMPLETED 的订单上。")

        say("\n  inventory rules (Day 15's rule, unchanged -- proof we did not break it)")
        sd = drift(SOLD_DRIFT)
        ld = drift(LOCKED_DRIFT)
        say("    sold   == sum(PAID+SHIPPED+COMPLETED units) -> %s drifting SKUs" % sd)
        say("    locked == sum(PENDING_PAYMENT units)         -> %s drifting SKUs" % ld)
        chk("★ sold conservation still holds (Day 15 rule untouched)", sd == "0")
        chk("★ locked conservation still holds", ld == "0")
        chk("no negative stock anywhere",
            one("SELECT count(*) FROM inventories WHERE available_stock < 0"
                " OR locked_stock < 0 OR sold_stock < 0").strip() == "0")
        say("\n  ★ 本日评价【不碰库存、不改订单状态】：sold / locked 口径零改动。")

    except _Abort:
        say("\n(aborted early -- cleanup below still runs)")

    finally:
        # ================================================== [12] cleanup
        say("\n" + "=" * 78)
        say("[12] CLEANUP -- remove this run's artifacts, restore the baseline")
        say("=" * 78)
        say("  orders to delete: %s" % (created or "(none)"))
        say("  ledger rows to delete: id > %d" % high_water)
        try:
            if created:
                ids = ",".join(str(o) for o in created)
                # ★ 评价按 order_id 精确删：只删本次靶子的，绝不清空表
                psql("DELETE FROM reviews WHERE order_id IN (%s);"
                     " DELETE FROM payments WHERE order_id IN (%s);"
                     " DELETE FROM order_items WHERE order_id IN (%s);"
                     " DELETE FROM orders WHERE id IN (%s);" % (ids, ids, ids, ids))
            psql("DELETE FROM inventory_logs WHERE id > %d;" % high_water)
            for sku in sorted(touched):
                b0 = base_all[sku]
                psql("UPDATE inventories SET available_stock = %d, locked_stock = %d,"
                     " sold_stock = %d, updated_at = CURRENT_TIMESTAMP"
                     " WHERE sku_id = %d;"
                     % (b0["available"], b0["locked"], b0["sold"], sku))
            chk("cleanup ran without SQL error", True)
        except Exception as e:                                        # noqa: BLE001
            say("  CLEANUP FAILED: %s" % e)
            chk("cleanup ran without SQL error", False)

        say("\n[13] VERIFY -- the database is byte-for-byte back at baseline")
        after_all = all_inv()
        for sku in sorted(after_all):
            tag = "restored" if after_all[sku] == base_all.get(sku) else "DRIFTED"
            say(inv_line(tag, sku, after_all[sku]))
        mismatches = [sku for sku in base_all if after_all.get(sku) != base_all[sku]]
        if mismatches:
            say("  MISMATCHED SKUs: %s" % mismatches)
        after_counts = row_counts()
        say("  rows orders/payments/order_items/inventory_logs/reviews = %s   (baseline %s)"
            % (after_counts, base_counts))
        chk("★★ all 7 SKUs identical to the baseline fingerprint", not mismatches)
        chk("★ row counts identical to baseline", after_counts == base_counts)
        chk("★ reviews back to the starting count (%d)" % base_reviews, review_count() == base_reviews)
        chk("no orphan order_items left", one(
            "SELECT count(*) FROM order_items oi LEFT JOIN orders o ON o.id = oi.order_id"
            " WHERE o.id IS NULL").strip() == "0")
        chk("no orphan payments left", one(
            "SELECT count(*) FROM payments p LEFT JOIN orders o ON o.id = p.order_id"
            " WHERE o.id IS NULL").strip() == "0")
        chk("no orphan reviews left", one(
            "SELECT count(*) FROM reviews r LEFT JOIN order_items oi ON oi.id = r.order_item_id"
            " WHERE oi.id IS NULL").strip() == "0")
        chk("no COMPLETED / SHIPPED order left behind by this run",
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
