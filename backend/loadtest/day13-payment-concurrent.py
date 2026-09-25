# -*- coding: utf-8 -*-
"""
Day 13 Step 3: concurrent PAYMENT load test.

Model: ONE shared account (demo / user_id = 1) and ONE target order.
20 threads fire POST /api/payments {orderId, method} at the SAME instant
(threading.Barrier) -- i.e. the user double-clicks "pay" 20 times, or a
retry storm hits the endpoint.

Two modes, two code shapes:

  mode=cas    the shipped code:
                  UPDATE orders SET status='PAID'
                   WHERE id=? AND status='PENDING_PAYMENT'
              The decision is INSIDE the SQL statement, so it is atomic.
              EXPECT: exactly 1 success, 19 x 400, exactly 1 payment row,
                      locked_stock -N / sold_stock +N exactly once.

  mode=naive  check-then-act (the classic bug):
                  SELECT status FROM orders;          -- looks payable
                  if (status == PENDING) UPDATE orders SET status='PAID';  -- no WHERE
              Every thread reads PENDING_PAYMENT *before* anyone commits, so
              every thread passes the check.
              EXPECT: 20 successes -> the order is PAID 20 times, 20 payment
                      rows are written, and locked_stock is decremented 20
                      times -> NEGATIVE stock.

Evidence for "how many times was inventory actually written" comes from a DB
trigger (pay13_stock_audit, created by day13-audit-setup.sql) that records
EVERY write to inventories -- polling from Python via `docker exec` is far too
slow to observe a 50ms race.

Usage:
    python day13-payment-concurrent.py <orderId> <cas|naive>

Output is ASCII-only on purpose (Windows console encoding safety); the Chinese
strings that come back from the API are printed via the reconfigured stdout.
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
THREADS = 20
USERNAME = "demo"
PASSWORD = "demo123"
METHODS = ["ALIPAY", "WECHAT", "BALANCE"]      # spread across the whitelist

import os
# ★ Portability (CI runs on Linux): MALLX_DOCKER overrides this path.
#   Unset locally => identical behaviour to before.
DOCKER = os.environ.get("MALLX_DOCKER") or r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"

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
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
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
    """psql 经 `docker exec` 回传时行尾会带 \\r，逐字段 strip 掉再比对。

    ★ 不 strip 的话 `"t\\r" == "t"` 恒为 False —— 断言会「假失败」，
      比真失败更费时间（要去查一个根本不存在的问题）。
    """
    p = [x.strip() for x in line.split(",")]
    return p if len(p) == n else None


def as_bool(s):
    """布尔值转 Python bool。

    ⚠️ 实测陷阱：psql 把布尔【列】显示成 `t`/`f`，但一旦参与 `||` 拼接，
    PG 用的是 bool 的输出函数 -> 得到 `true`/`false` 全词。
    所以只认 `"t"` 会恒为假，两种写法都要接住。
    """
    return s.lower() in ("t", "true")


def order_row(order_id):
    out = psql("SELECT status || ',' || (paid_at IS NOT NULL) FROM orders WHERE id = %d" % order_id)
    p = fields(out, 2)
    if p is None:
        raise RuntimeError("bad order row: " + repr(out))
    return p[0], as_bool(p[1])


def items_of(order_id):
    """[(sku_id, quantity), ...] -- straight from the server-side snapshot."""
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
    out = psql("SELECT count(*) || ',' || count(DISTINCT payment_no) || ',' || "
               "coalesce(sum(amount), 0) FROM payments WHERE order_id = %d" % order_id)
    p = fields(out, 3)
    if p is None:
        raise RuntimeError("bad payment stats: " + repr(out))
    return dict(rows=int(p[0]), distinct_no=int(p[1]), total_amount=p[2])


def seq_last(table):
    """自增序列当前值。★ 序列【不参与回滚】—— 回滚掉的 INSERT 也会烧掉一个 id。
    于是它成了「到底有多少个线程走到过 INSERT」的旁证。"""
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


# -------------------------------------------------- truly simultaneous firing
def warm_conn():
    """预先建立并保持一条 TCP 连接，让 POST 一触即发。

    ★ 为什么需要它（实测教训）：`api()` 走 `urllib.request.urlopen()`，每次调用
      【新开一条 TCP 连接】，而建连被 GIL 串行化 → 20 个"同时"启动的线程实际
      间隔 ~8ms 打达服务端（全程 165ms）。结果：竞态窗口被客户端自己遮掉大半，
      对照组只跑出 7 笔重复支付而不是 20 笔。
      先把 socket 连好（GET /api/hello 预热，服务端 keep-alive 保持连接），
      屏障一放行，20 个 POST 才是真的同一瞬间到达。
    """
    conn = http.client.HTTPConnection("127.0.0.1", 8080, timeout=90)
    conn.request("GET", "/api/hello")
    conn.getresponse().read()          # 读干净响应体，keep-alive 连接才不会被丢弃
    return conn


def post_payment(conn, token, order_id, method):
    """在【已建好】的连接上发 POST /api/payments，返回 (status, body)。"""
    payload = json.dumps({"orderId": order_id, "method": method}).encode("utf-8")
    conn.request("POST", "/api/payments", body=payload, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + token,
    })
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
    method = METHODS[idx % len(METHODS)]
    conn = warm_conn()                 # ← 必须先建连，屏障才有意义
    # ---- sync point: all threads fire POST /api/payments at the same instant
    barrier.wait()
    try:
        st, body = post_payment(conn, token, order_id, method)
    except Exception:
        # 连接偶发失效（服务端回收空闲连接）→ 退化成普通请求，别让一个线程拖垮整轮
        st, body = api("POST", "/api/payments", token=token,
                       body={"orderId": order_id, "method": method})
    finally:
        try:
            conn.close()
        except Exception:
            pass
    data = body.get("data") if isinstance(body.get("data"), dict) else None
    rec = {"idx": idx, "http": st, "code": body.get("code"),
           "message": body.get("message"),
           "paymentNo": (data or {}).get("paymentNo")}
    with rlock:
        results.append(rec)


def main():
    if len(sys.argv) < 3:
        print("usage: day13-payment-concurrent.py <orderId> <cas|naive>")
        return 2
    order_id = int(sys.argv[1])
    mode = sys.argv[2].lower()
    if mode not in ("cas", "naive"):
        print("mode must be 'cas' or 'naive'")
        return 2

    items = items_of(order_id)
    sku_ids = [s for s, _ in items]
    qty_total = sum(q for _, q in items)

    status_before, paid_before = order_row(order_id)
    inv_before = inv_rows(sku_ids)
    pay_before = pay_stats(order_id)
    seq_before = seq_last("payments")

    print("=" * 72)
    print("Day 13 Step 3 -- concurrent PAYMENT load test")
    print("mode          :", mode)
    print("target        :", BASE, " order #%d" % order_id)
    print("account       :", USERNAME, "(one shared account, %d threads)" % THREADS)
    print("order status  :", status_before, " paid_at set:", paid_before)
    print("order items   :", " + ".join("sku%d x%d" % (s, q) for s, q in items))
    print("payments now  : rows=%d distinct_no=%d sum=%s" % (
        pay_before["rows"], pay_before["distinct_no"], pay_before["total_amount"]))
    for s in sku_ids:
        r = inv_before[s]
        print("stock before  : sku%d total=%d available=%d locked=%d sold=%d id_ok=%s" % (
            s, r["total"], r["available"], r["locked"], r["sold"], r["identity_ok"]))

    st, body = api("POST", "/api/auth/login", body={"username": USERNAME, "password": PASSWORD})
    token = (body.get("data") or {}).get("token")
    print("login         : http=%s token_ok=%s" % (st, bool(token)))
    if not token:
        print("ABORT: cannot obtain token ->", body)
        return 1

    t0 = time.time()
    workers = [threading.Thread(target=worker, args=(i, token, order_id)) for i in range(THREADS)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    elapsed = time.time() - t0

    print("\n--- per-thread (elapsed %.2fs) ---" % elapsed)
    for r in sorted(results, key=lambda x: x["idx"]):
        line = "  t%02d http=%s code=%s" % (r["idx"], r["http"], r["code"])
        if r["paymentNo"]:
            line += " paymentNo=%s" % r["paymentNo"]
        elif r["message"]:
            line += " msg=%s" % r["message"]
        print(line)

    ok = [r for r in results if r["code"] == 200]
    bad = [r for r in results if r["code"] != 200]
    codes = Counter(r["code"] for r in bad)
    msgs = Counter(r["message"] for r in bad)

    status_after, paid_after = order_row(order_id)
    inv_after = inv_rows(sku_ids)
    pay_after = pay_stats(order_id)
    audit = audit_rows(sku_ids)

    pay_delta = pay_after["rows"] - pay_before["rows"]

    print("\n--- summary ---")
    print("success       : %d" % len(ok))
    print("failed        : %d" % len(bad))
    print("fail codes    : %s" % dict(codes))
    print("fail messages : %s" % dict(msgs))
    print("order status  : %s  paid_at set: %s" % (status_after, paid_after))
    print("payments      : rows=%d (+%d) distinct_no=%d sum=%s" % (
        pay_after["rows"], pay_delta, pay_after["distinct_no"], pay_after["total_amount"]))
    seq_after = seq_last("payments")
    print("payments seq  : %d -> %d  (consumed %d ids)" % (
        seq_before, seq_after, seq_after - seq_before))
    for s in sku_ids:
        a, b = inv_before[s], inv_after[s]
        print("stock after   : sku%d total=%d available=%d locked=%d sold=%d id_ok=%s  "
              "(d_avail=%+d d_locked=%+d d_sold=%+d)" % (
                  s, b["total"], b["available"], b["locked"], b["sold"], b["identity_ok"],
                  b["available"] - a["available"],
                  b["locked"] - a["locked"],
                  b["sold"] - a["sold"]))

    print("\n--- stock audit: EVERY write to inventories (recorded by DB trigger) ---")
    if not audit:
        print("  (no rows -- did day13-audit-setup.sql run?)")
    for i, (sid, av, lk, sd) in enumerate(audit, 1):
        print("  #%02d  sku=%d  available=%4d  locked=%4d  sold=%4d" % (i, sid, av, lk, sd))

    # ------------------------------------------------------------ assertions
    checks = [
        ("order ends up PAID", status_after == "PAID"),
        ("paid_at written", paid_after),
        ("payment_no all unique", pay_after["rows"] == pay_after["distinct_no"]),
    ]

    if mode == "cas":
        checks += [
            ("EXACTLY 1 success (got %d)" % len(ok), len(ok) == 1),
            ("19 rejected (got %d)" % len(bad), len(bad) == THREADS - 1),
            ("all rejections are code 400", all(r["code"] == 400 for r in bad)),
            ("payments +1 row (got %+d)" % pay_delta, pay_delta == 1),
            ("payments sum == order pay_amount", pay_after["total_amount"] ==
             psql("SELECT pay_amount FROM orders WHERE id = %d" % order_id)),
            ("audit rows == %d (one write per SKU)" % len(sku_ids), len(audit) == len(sku_ids)),
            ("no negative stock anywhere", all(av >= 0 and lk >= 0 and sd >= 0
                                               for _, av, lk, sd in audit)),
        ]
        for s, q in items:
            a, b = inv_before[s], inv_after[s]
            checks += [
                ("sku%d locked %d -> %d (exactly -%d)" % (s, a["locked"], b["locked"], q),
                 b["locked"] == a["locked"] - q),
                ("sku%d sold %d -> %d (exactly +%d)" % (s, a["sold"], b["sold"], q),
                 b["sold"] == a["sold"] + q),
                ("sku%d available UNCHANGED (%d)" % (s, a["available"]),
                 b["available"] == a["available"]),
            ]
    else:
        checks += [
            ("ALL %d succeeded (got %d)" % (THREADS, len(ok)), len(ok) == THREADS),
            ("payments +%d rows (got %+d)" % (THREADS, pay_delta), pay_delta == THREADS),
            ("money collected %d times over" % THREADS,
             pay_after["total_amount"] == psql("SELECT (pay_amount * %d)::numeric FROM orders WHERE id = %d"
                                               % (THREADS, order_id))),
            ("audit rows == %d (each SKU written %d times)" % (len(sku_ids) * THREADS, THREADS),
             len(audit) == len(sku_ids) * THREADS),
            ("DAMAGE: some stock went NEGATIVE", any(av < 0 or lk < 0 or sd < 0
                                                     for _, av, lk, sd in audit)),
        ]
        for s, q in items:
            a, b = inv_before[s], inv_after[s]
            checks += [
                ("sku%d locked %d -> %d (decremented %d times)" % (s, a["locked"], b["locked"], THREADS),
                 b["locked"] == a["locked"] - q * THREADS),
                ("sku%d sold %d -> %d (incremented %d times)" % (s, a["sold"], b["sold"], THREADS),
                 b["sold"] == a["sold"] + q * THREADS),
                ("sku%d available STILL unchanged (%d)" % (s, a["available"]),
                 b["available"] == a["available"]),
            ]

    # ---- the identity holds even on corrupt data: total = avail + locked + sold
    checks += [
        ("identity total=avail+locked+sold holds EVEN NOW",
         all(inv_after[s]["identity_ok"] for s in sku_ids)),
        ("payments seq consumed %d ids -> all %d threads really reached the INSERT"
         % (THREADS, THREADS), seq_after - seq_before == THREADS),
    ]

    print("\n--- assertions ---")
    passed = 0
    for name, good in checks:
        print("  [%s] %s" % ("PASS" if good else "FAIL", name))
        passed += 1 if good else 0

    print("\nRESULT: %d/%d passed" % (passed, len(checks)))
    if mode == "cas":
        print("VERDICT:", "SAFE -- one order, one payment" if passed == len(checks)
              else "UNEXPECTED -- investigate")
    else:
        print("VERDICT:", "DOUBLE CHARGE CONFIRMED -- one order paid %d times" % len(ok)
              if len(ok) > 1 else "NOT REPRODUCED -- raise the pool size and retry")
    return 0


if __name__ == "__main__":
    sys.exit(main())
