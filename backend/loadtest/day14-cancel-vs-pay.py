# -*- coding: utf-8 -*-
"""
Day 14 Step 2 -- CANCEL vs PAY, race for the SAME status slot.

Day 13 raced 20 PAYMENTS against each other and proved that the CAS
(`WHERE status='PENDING_PAYMENT'`) lets exactly one through.

This is a strictly harder race, because the two competitors want OPPOSITE
outcomes from the SAME state:

    PENDING_PAYMENT --pay--> PAID       inventory: locked -> sold
    PENDING_PAYMENT --cancel--> CANCELLED  inventory: locked -> available

One thread wants to SELL the goods, the other wants to GIVE THEM BACK.
20 threads fire at the same instant (threading.Barrier), even index = cancel,
odd index = pay. An order can end up in exactly one of those states.

  mode=cas    the shipped code -- both statements carry their guard:
                  UPDATE orders SET status='PAID'      WHERE id=? AND status='PENDING_PAYMENT'
                  UPDATE orders SET status='CANCELLED' WHERE id=? AND status='PENDING_PAYMENT'
              EXPECT: exactly ONE winner overall. The loser's whole transaction
                      rolls back. Stock moves in ONE direction only.

  mode=naive  both guards stripped:
                  UPDATE orders SET status='PAID'      WHERE id=?
                  UPDATE orders SET status='CANCELLED' WHERE id=?
                  ...and both inventory guards removed too
              EXPECT: BOTH directions succeed. The same goods get refunded AND
                      sold -> availability goes UP while sold also goes UP ->
                      goods appear out of thin air, and locked_stock goes
                      negative. ★ And `total = avail + locked + sold` STILL
                      HOLDS -- arithmetic conservation cannot see this bug.

★ The PG detail worth remembering: under READ COMMITTED, an UPDATE that hits a
  locked row waits, then RE-EVALUATES its WHERE clause (EvalPlanQual). So a
  guarded UPDATE is safe on its own. The bug in the naive version is not
  "using UPDATE" -- it is "the UPDATE has no condition".

Evidence for "how many times was inventory really written" comes from the DB
trigger in day13-audit-setup.sql (reused as-is: it is a generic AFTER UPDATE
audit on inventories, the "13" in the table name is just history).

Usage:
    python day14-cancel-vs-pay.py <orderId|0> <cas|naive>
    orderId 0 -> the script places a fresh PENDING_PAYMENT order itself
"""
import http.client
import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter

BASE = "http://127.0.0.1:8080"
HOST, PORT = "127.0.0.1", 8080
THREADS = 20
USERNAME, PASSWORD = "demo", "demo123"
TARGET_SKU = 4            # used only when the script creates its own target order
ADDRESS_ID = 2
METHODS = ["ALIPAY", "WECHAT", "BALANCE"]

DOCKER = r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ---------------------------------------------------------------- http helper
def api(method, path, token=None, body=None, timeout=90):
    headers = {}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:                                          # noqa: BLE001
            return e.code, {"raw": raw}
    except Exception as e:                                          # noqa: BLE001
        return -1, {"error": repr(e)}


# ---------------------------------------------------------------- db helpers
def psql(sql):
    p = subprocess.run(
        [DOCKER, "exec", "-i", "-e", "PGCLIENTENCODING=UTF8",
         "mallx-postgres", "psql", "-U", "mallx", "-d", "mallx",
         "-t", "-A", "-F", "|", "-c", sql],
        capture_output=True)
    return p.stdout.decode("utf-8", "replace").strip()


def fields(line, n):
    """psql 经 `docker exec` 回传时行尾带 \\r，逐字段 strip 再比对。"""
    p = [x.strip() for x in line.split(",")]
    return p if len(p) == n else None


def as_bool(s):
    """⚠️ psql 单独显示布尔列是 `t`/`f`，但参与 `||` 拼接后是 `true`/`false` 全词。"""
    return s.lower() in ("t", "true")


def order_row(order_id):
    out = psql("SELECT status || ',' || (paid_at IS NOT NULL) || ',' || "
               "(cancelled_at IS NOT NULL) FROM orders WHERE id = %d" % order_id)
    p = fields(out, 3)
    if p is None:
        raise RuntimeError("bad order row: " + repr(out))
    return p[0], as_bool(p[1]), as_bool(p[2])


def items_of(order_id):
    out = psql("SELECT sku_id || ',' || quantity FROM order_items "
               "WHERE order_id = %d ORDER BY sku_id" % order_id)
    res = []
    for line in out.splitlines():
        p = fields(line, 2)
        if p is not None:
            res.append((int(p[0]), int(p[1])))
    if not res:
        raise RuntimeError("order %d has no items" % order_id)
    return res


def inv_rows(sku_ids):
    sql = ("SELECT sku_id || ',' || total_stock || ',' || available_stock || ',' || "
           "locked_stock || ',' || sold_stock || ',' || "
           "(total_stock = available_stock + locked_stock + sold_stock) "
           "FROM inventories WHERE sku_id IN (%s) ORDER BY sku_id"
           % ",".join(str(s) for s in sku_ids))
    d = {}
    for line in psql(sql).splitlines():
        p = fields(line, 6)
        if p is not None:
            d[int(p[0])] = dict(total=int(p[1]), available=int(p[2]),
                                locked=int(p[3]), sold=int(p[4]),
                                identity_ok=as_bool(p[5]))
    return d


def pay_stats(order_id):
    out = psql("SELECT count(*) || ',' || coalesce(sum(amount),0) FROM payments "
               "WHERE order_id = %d" % order_id)
    p = fields(out, 2)
    return dict(rows=int(p[0]), total_amount=p[1])


def seq_last(table):
    """★ 序列不参与回滚 —— 回滚掉的 INSERT 也烧掉一个 id，于是它成了
    「到底有多少个线程真的走到过 INSERT」的旁证。"""
    out = psql("SELECT last_value FROM %s_id_seq" % table)
    try:
        return int(out.strip())
    except ValueError:
        return -1


def audit_rows(sku_ids):
    out = psql("SELECT sku_id || ',' || available || ',' || locked || ',' || sold "
               "FROM pay13_stock_audit WHERE sku_id IN (%s) ORDER BY id"
               % ",".join(str(s) for s in sku_ids))
    rows = []
    for line in out.splitlines():
        p = fields(line, 4)
        if p is not None:
            rows.append((int(p[0]), int(p[1]), int(p[2]), int(p[3])))
    return rows


def conservation_drift():
    """业务守恒：locked 应 == Σ(未支付明细)，sold 应 == Σ(已售出去的明细)。
    ★ sold 口径：Day 15 起是 {PAID, SHIPPED, COMPLETED} —— 发货/收货都不动 sold，
      但会把订单挪出 PAID，只认 PAID 会报【假漂移】（详见 Day-15 文档 §0.2）。
    返回漂移的 SKU 列表（正常应为空）。"""
    out = psql(
        "SELECT coalesce(string_agg(t.sku_id::text, ','), '-') FROM ("
        " SELECT i.sku_id FROM inventories i"
        " LEFT JOIN (SELECT oi.sku_id, sum(oi.quantity) AS want FROM order_items oi"
        "            JOIN orders o ON o.id=oi.order_id WHERE o.status='PENDING_PAYMENT'"
        "            GROUP BY oi.sku_id) l ON l.sku_id=i.sku_id"
        " LEFT JOIN (SELECT oi.sku_id, sum(oi.quantity) AS want FROM order_items oi"
        "            JOIN orders o ON o.id=oi.order_id WHERE o.status IN ('PAID','SHIPPED','COMPLETED')"
        "            GROUP BY oi.sku_id) s ON s.sku_id=i.sku_id"
        " WHERE i.locked_stock <> coalesce(l.want,0)"
        "    OR i.sold_stock <> coalesce(s.want,0)"
        ") t")
    return out.strip()


# ------------------------------------------------ create a target order (opt)
def create_target_order(token):
    """Put TARGET_SKU x1 in the cart, select it, order it. Returns the new order id."""
    st, b = api("GET", "/api/cart", token=token)
    target = None
    for it in ((b.get("data") or {}).get("items") or []):
        if it.get("skuId") == TARGET_SKU:
            target = it
    if target is None:
        api("POST", "/api/cart", token=token, body={"skuId": TARGET_SKU, "quantity": 1})
        st, b = api("GET", "/api/cart", token=token)
        for it in ((b.get("data") or {}).get("items") or []):
            if it.get("skuId") == TARGET_SKU:
                target = it
    if target is None:
        raise RuntimeError("could not get sku%d into the cart" % TARGET_SKU)
    api("PUT", "/api/cart/%s/selected" % target["id"], token=token, body={"selected": True})
    st, b = api("POST", "/api/orders", token=token, body={"addressId": ADDRESS_ID})
    oid = b.get("data") if st == 200 else None
    if not isinstance(oid, int):
        raise RuntimeError("could not create the target order: %s" % b)
    return oid


# -------------------------------------------------- truly simultaneous firing
def warm_conn():
    """预建 TCP 连接，让两个方向的请求一触即发。

    ★ 实测教训（Day 13）：`urllib` 每次新开 TCP，建连被 GIL 串行化 →
      20 个"同时"的请求实际间隔上百毫秒，竞态窗口被客户端自己遮掉大半。
      先 GET /api/hello 把 socket 建好，屏障一放行才是真的同时到达。
    """
    conn = http.client.HTTPConnection(HOST, PORT, timeout=90)
    conn.request("GET", "/api/hello")
    conn.getresponse().read()
    return conn


def fire(conn, token, kind, order_id, method):
    """在已建好的连接上发一次请求。kind = 'cancel' | 'pay'。"""
    if kind == "cancel":
        path = "/api/orders/%d/cancel" % order_id
        payload = None
    else:
        path = "/api/payments"
        payload = json.dumps({"orderId": order_id, "method": method}).encode("utf-8")
    headers = {"Authorization": "Bearer " + token}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    conn.request("POST", path, body=payload, headers=headers)
    r = conn.getresponse()
    raw = r.read().decode("utf-8", "replace")
    try:
        return r.status, json.loads(raw)
    except ValueError:
        return r.status, {"raw": raw}


# ---------------------------------------------------------------- workers
results = []
rlock = threading.Lock()
barrier = threading.Barrier(THREADS)


def worker(idx, token, order_id):
    """偶数号线程取消，奇数号线程支付 —— 两个相反的方向抢同一个状态位。"""
    kind = "cancel" if idx % 2 == 0 else "pay"
    method = METHODS[idx % len(METHODS)]
    conn = warm_conn()
    barrier.wait()
    try:
        st, body = fire(conn, token, kind, order_id, method)
    except Exception:                                               # noqa: BLE001
        # 连接偶发失效 → 退化成普通请求，别让一个线程拖垮整轮
        if kind == "cancel":
            st, body = api("POST", "/api/orders/%d/cancel" % order_id, token=token)
        else:
            st, body = api("POST", "/api/payments", token=token,
                           body={"orderId": order_id, "method": method})
    finally:
        try:
            conn.close()
        except Exception:
            pass
    with rlock:
        results.append({"idx": idx, "kind": kind, "http": st,
                        "code": body.get("code"), "message": body.get("message")})


def main():
    if len(sys.argv) < 3:
        print("usage: day14-cancel-vs-pay.py <orderId|0> <cas|naive>")
        return 2
    order_id = int(sys.argv[1])
    mode = sys.argv[2].lower()
    if mode not in ("cas", "naive"):
        print("mode must be 'cas' or 'naive'")
        return 2

    print("=" * 76)
    print("Day 14 Step 2 -- CANCEL vs PAY race for one order's status slot")
    print("mode   :", mode)
    print("target :", BASE)
    print("threads: %d (%d cancel on even idx + %d pay on odd idx), released together"
          % (THREADS, THREADS // 2, THREADS // 2))
    print("=" * 76)

    st, body = api("POST", "/api/auth/login", body={"username": USERNAME, "password": PASSWORD})
    token = (body.get("data") or {}).get("token")
    if not token:
        print("ABORT: cannot obtain token ->", body)
        return 1

    if order_id == 0:
        order_id = create_target_order(token)
        print("built a fresh target order: #%d" % order_id)

    status_before, paid_before, cancel_before = order_row(order_id)
    items = items_of(order_id)
    sku_ids = [s for s, _ in items]
    qty_total = sum(q for _, q in items)
    inv_before = inv_rows(sku_ids)
    pay_before = pay_stats(order_id)
    seq_before = seq_last("payments")
    # ★ 审计行数的【起点】：脚本自己造的靶子，下单那一刻就已经写过一次 inventories
    #   （deductStock）。断言必须看「比赛期间新增了几行」，而不是绝对行数。
    audit_before_n = len(audit_rows(sku_ids))

    print("order  : #%d status=%s paid_at=%s cancelled_at=%s"
          % (order_id, status_before, paid_before, cancel_before))
    print("items  : %s" % " + ".join("sku%d x%d" % (s, q) for s, q in items))
    print("payments before: rows=%d sum=%s" % (pay_before["rows"], pay_before["total_amount"]))
    for s in sku_ids:
        r = inv_before[s]
        print("stock before   : sku%d total=%d available=%d locked=%d sold=%d id_ok=%s"
              % (s, r["total"], r["available"], r["locked"], r["sold"], r["identity_ok"]))

    if status_before != "PENDING_PAYMENT":
        print("ABORT: target order must be PENDING_PAYMENT, it is %s" % status_before)
        return 1

    t0 = time.time()
    ws = [threading.Thread(target=worker, args=(i, token, order_id)) for i in range(THREADS)]
    for w in ws:
        w.start()
    for w in ws:
        w.join()
    elapsed = time.time() - t0

    print("\n--- per-thread (elapsed %.2fs) ---" % elapsed)
    for r in sorted(results, key=lambda x: x["idx"]):
        print("  t%02d %-6s http=%s code=%s %s"
              % (r["idx"], r["kind"], r["http"], r["code"], r["message"] or ""))

    cancel_ok = [r for r in results if r["kind"] == "cancel" and r["code"] == 200]
    pay_ok = [r for r in results if r["kind"] == "pay" and r["code"] == 200]
    cancel_bad = [r for r in results if r["kind"] == "cancel" and r["code"] != 200]
    pay_bad = [r for r in results if r["kind"] == "pay" and r["code"] != 200]

    status_after, paid_after, cancel_after = order_row(order_id)
    inv_after = inv_rows(sku_ids)
    pay_after = pay_stats(order_id)
    seq_after = seq_last("payments")
    audit = audit_rows(sku_ids)
    drift = conservation_drift()

    print("\n--- summary ---")
    print("cancel success : %d   (fail %d %s)" % (
        len(cancel_ok), len(cancel_bad), dict(Counter(r["code"] for r in cancel_bad))))
    print("pay    success : %d   (fail %d %s)" % (
        len(pay_ok), len(pay_bad), dict(Counter(r["code"] for r in pay_bad))))
    print("pay fail msgs  : %s" % dict(Counter(r["message"] for r in pay_bad)))
    print("cancel fail msgs: %s" % dict(Counter(r["message"] for r in cancel_bad)))
    print("order final    : status=%s paid_at=%s cancelled_at=%s"
          % (status_after, paid_after, cancel_after))
    print("payments       : rows=%d (%+d) sum=%s"
          % (pay_after["rows"], pay_after["rows"] - pay_before["rows"], pay_after["total_amount"]))
    print("payments seq   : %d -> %d (consumed %d)" % (seq_before, seq_after, seq_after - seq_before))
    for s in sku_ids:
        a, b = inv_before[s], inv_after[s]
        print("stock final    : sku%d total=%d available=%d locked=%d sold=%d id_ok=%s  "
              "(d_avail=%+d d_locked=%+d d_sold=%+d)"
              % (s, b["total"], b["available"], b["locked"], b["sold"], b["identity_ok"],
                 b["available"] - a["available"],
                 b["locked"] - a["locked"],
                 b["sold"] - a["sold"]))

    print("\n--- stock audit: EVERY write to inventories (recorded by DB trigger) ---")
    print("  rows present before the race: %d (this script's own ordering step,"
          " i.e. deductStock)" % audit_before_n)
    if not audit:
        print("  (no rows -- did day13-audit-setup.sql run?)")
    for i, (sid, av, lk, sd) in enumerate(audit, 1):
        tag = "before race" if i <= audit_before_n else "during race"
        print("  #%02d  sku=%d  available=%4d  locked=%4d  sold=%4d   [%s]"
              % (i, sid, av, lk, sd, tag))
    print("  -> writes during the race: %d" % (len(audit) - audit_before_n))

    print("\n--- business conservation (locked / sold vs order items) ---")
    print("  drifting SKUs: %s   <-- '' / '-' means the books balance" % drift)

    # ------------------------------------------------------------ assertions
    checks = [
        ("order ends in PAID or CANCELLED (got %s)" % status_after,
         status_after in ("PAID", "CANCELLED")),
    ]

    if mode == "cas":
        checks += [
            ("★ EXACTLY ONE winner overall (cancel %d + pay %d)"
             % (len(cancel_ok), len(pay_ok)), len(cancel_ok) + len(pay_ok) == 1),
            ("the two timestamps are mutually exclusive",
             not (paid_after and cancel_after)),
            ("all losers rejected with 400",
             all(r["code"] == 400 for r in cancel_bad + pay_bad)),
            ("order status matches the winning direction",
             (status_after == "PAID" and len(pay_ok) == 1)
             or (status_after == "CANCELLED" and len(cancel_ok) == 1)),
            ("paid_at / cancelled_at written only for the winner",
             (paid_after and not cancel_after) or (cancel_after and not paid_after)),
            ("payments +1 row if PAY won, +0 if CANCEL won (delta=%+d)"
             % (pay_after["rows"] - pay_before["rows"]),
             (pay_after["rows"] - pay_before["rows"]) == (1 if pay_ok else 0)),
            ("payments seq consumed exactly %d ids (one per pay thread)"
             % (THREADS // 2), seq_after - seq_before == THREADS // 2),
            ("★ the race wrote inventory exactly %d time(s) -- stock moved ONCE"
             % len(sku_ids), len(audit) - audit_before_n == len(sku_ids)),
            ("no negative stock anywhere", all(av >= 0 and lk >= 0 and sd >= 0
                                               for _, av, lk, sd in audit)),
        ]
        for s, q in items:
            a, b = inv_before[s], inv_after[s]
            if status_after == "PAID":
                checks += [
                    ("sku%d PAY won: locked -%d" % (s, q), b["locked"] == a["locked"] - q),
                    ("sku%d PAY won: sold +%d" % (s, q), b["sold"] == a["sold"] + q),
                    ("sku%d PAY won: available UNCHANGED (%d)" % (s, a["available"]),
                     b["available"] == a["available"]),
                ]
            else:
                checks += [
                    ("sku%d CANCEL won: locked -%d" % (s, q), b["locked"] == a["locked"] - q),
                    ("sku%d CANCEL won: available +%d" % (s, q), b["available"] == a["available"] + q),
                    ("sku%d CANCEL won: sold UNCHANGED (%d)" % (s, a["sold"]),
                     b["sold"] == a["sold"]),
                ]
    else:
        # 对照组：两个方向都能成功 → 同一件货既退回可售池、又算进已售
        checks += [
            ("DAMAGE: BOTH directions succeeded (cancel %d, pay %d)"
             % (len(cancel_ok), len(pay_ok)), len(cancel_ok) >= 1 and len(pay_ok) >= 1),
            ("DAMAGE: BOTH timestamps written -- the order is paid AND cancelled at once",
             paid_after and cancel_after),
            ("★ DAMAGE: business conservation BROKEN (drifting skus: %s)" % drift,
             drift != "-"),
            ("DAMAGE: money collected %d times (payments +%d)"
             % (len(pay_ok), pay_after["rows"] - pay_before["rows"]),
             pay_after["rows"] - pay_before["rows"] == len(pay_ok)),
        ]
        for s, q in items:
            a, b = inv_before[s], inv_after[s]
            checks += [
                ("DAMAGE: sku%d available went UP (%+d) -- goods refunded"
                 % (s, b["available"] - a["available"]), b["available"] > a["available"]),
                ("DAMAGE: sku%d sold went UP (%+d) -- SAME goods also sold"
                 % (s, b["sold"] - a["sold"]), b["sold"] > a["sold"]),
                ("DAMAGE: sku%d locked decremented once per successful thread (%+d)"
                 % (s, b["locked"] - a["locked"]),
                 b["locked"] == a["locked"] - q * (len(cancel_ok) + len(pay_ok))),
                ("DAMAGE: sku%d locked is NEGATIVE now (%d)" % (s, b["locked"]), b["locked"] < 0),
            ]
        checks += [
            ("DAMAGE: the race wrote inventory %d times -- one per successful thread"
             % (len(sku_ids) * (len(cancel_ok) + len(pay_ok))),
             len(audit) - audit_before_n == len(sku_ids) * (len(cancel_ok) + len(pay_ok))),
        ]

    # ---- 两条模式都要验的：恒等式
    checks += [
        ("identity total=avail+locked+sold holds EVEN NOW",
         all(inv_after[s]["identity_ok"] for s in sku_ids)),
    ]
    if mode == "cas":
        checks += [
            ("★ business conservation intact (locked/sold match the order items)",
             drift == "-"),
            ("★ money was NOT double-charged (payments delta <= 1)",
             (pay_after["rows"] - pay_before["rows"]) <= 1),
        ]

    print("\n--- assertions ---")
    passed = 0
    for name, good in checks:
        print("  [%s] %s" % ("PASS" if good else "FAIL", name))
        passed += 1 if good else 0

    print("\nRESULT: %d/%d passed" % (passed, len(checks)))
    if mode == "cas":
        print("VERDICT:", "SAFE -- the two exits really are exclusive"
              if passed == len(checks) else "UNEXPECTED -- investigate")
    else:
        print("VERDICT:", "DOUBLE-SPEND CONFIRMED -- goods refunded AND sold (%d cancel + %d pay)"
              % (len(cancel_ok), len(pay_ok)) if len(cancel_ok) and len(pay_ok)
              else "NOT REPRODUCED -- raise the pool size and retry")
    return 0


if __name__ == "__main__":
    sys.exit(main())
