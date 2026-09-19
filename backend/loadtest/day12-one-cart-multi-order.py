# -*- coding: utf-8 -*-
"""
Day 12 Step 3 (extra): ONE CART, MANY ORDERS -- the missing idempotency guard.

A single user, a single cart line (sku 3 x 1), deliberately plentiful stock (100).
N threads fire POST /api/orders at the same instant holding the SAME token.

createFromCart is:
    read selected cart  ->  deduct stock  ->  insert order  ->  clear cart
All threads read the SAME cart row before any of them commits, so each one happily
creates its own order. Result: 1 item in the cart, MANY orders in the database.

Note this is NOT an oversell -- the stock arithmetic stays perfectly consistent
(available drops by exactly N, locked rises by exactly N). It is a missing
idempotency guard on the ORDER side, and it is precisely the shape of the
"user double-clicks Submit" bug that Day 13+ has to fix.

Run this against the CORRECT (conditional UPDATE) build -- it reproduces either way.

Output is ASCII-only on purpose (Windows console encoding safety).
"""
import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter

BASE = "http://127.0.0.1:8080"
THREADS = 10
USERNAME = "demo"
PASSWORD = "demo123"
ADDRESS_ID = 1            # demo user's address kept from Step 2
SKU_ID = 3
BUY_QTY = 1
STOCK = 100

DOCKER = r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def api(method, path, token=None, body=None, timeout=60):
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
    except Exception as e:                                    # noqa: BLE001
        return -1, {"error": repr(e)}


def psql(sql):
    p = subprocess.run(
        [DOCKER, "exec", "-i", "-e", "PGCLIENTENCODING=UTF8",
         "mallx-postgres", "psql", "-U", "mallx", "-d", "mallx",
         "-t", "-A", "-F", "|", "-c", sql],
        capture_output=True)
    return p.stdout.decode("utf-8", "replace").strip()


results = []
rlock = threading.Lock()
barrier = threading.Barrier(THREADS)


def worker(token, idx):
    barrier.wait()
    st, body = api("POST", "/api/orders", token=token, body={"addressId": ADDRESS_ID})
    data = body.get("data")
    order_id = data.get("id") if isinstance(data, dict) else data
    with rlock:
        results.append((idx, st, body.get("code"), body.get("message"), order_id))


def main():
    # ---- fixture: plentiful stock, empty demo cart, clean audit
    psql("UPDATE inventories SET total_stock = %d, available_stock = %d, "
         "locked_stock = 0, sold_stock = 0 WHERE sku_id = %d" % (STOCK, STOCK, SKU_ID))
    psql("DELETE FROM cart_items WHERE user_id = 1")
    psql("TRUNCATE lt_stock_audit")

    st, body = api("POST", "/api/auth/login", body={"username": USERNAME, "password": PASSWORD})
    token = (body.get("data") or {}).get("token")
    if not token:
        print("FATAL: login failed ->", st, body)
        sys.exit(1)

    st, body = api("POST", "/api/cart", token=token, body={"skuId": SKU_ID, "quantity": BUY_QTY})
    print("add to cart  : http=%s code=%s" % (st, body.get("code")))
    st, body = api("GET", "/api/cart", token=token)
    cart_rows = len((body.get("data") or {}).get("items", []))
    print("cart rows    : %d (all selected to buy)" % cart_rows)

    orders_before = int(psql("SELECT count(*) FROM orders WHERE user_id = 1"))
    stock_before = psql("SELECT available_stock || '/' || locked_stock FROM inventories "
                        "WHERE sku_id = %d" % SKU_ID)

    print("=" * 68)
    print("Day 12 Step 3 (extra) -- one cart, many orders")
    print("user         : %s (single account, single cart, 1 item in it)" % USERNAME)
    print("threads      : %d  all POST /api/orders with the SAME token" % THREADS)
    print("stock before : %s (available/locked)" % stock_before)
    print("orders before: %d" % orders_before)

    t0 = time.time()
    ws = [threading.Thread(target=worker, args=(token, i)) for i in range(THREADS)]
    for w in ws:
        w.start()
    for w in ws:
        w.join()
    elapsed = time.time() - t0

    print("\n--- per-thread (elapsed %.2fs) ---" % elapsed)
    for idx, st, code, msg, oid in sorted(results):
        line = "  thread=%2d http=%s code=%s" % (idx, st, code)
        if code == 200:
            line += "  orderId=%s" % oid
        elif msg:
            line += "  msg=%s" % msg
        print(line)

    ok = [r for r in results if r[2] == 200]
    bad = [r for r in results if r[2] != 200]
    orders_after = int(psql("SELECT count(*) FROM orders WHERE user_id = 1"))
    sold = orders_after - orders_before
    stock_after = psql("SELECT available_stock || '/' || locked_stock FROM inventories "
                       "WHERE sku_id = %d" % SKU_ID)
    ids = psql("SELECT string_agg(id::text, ',' ORDER BY id) FROM orders WHERE user_id = 1")

    print("\n--- summary ---")
    print("success      : %d" % len(ok))
    print("failed       : %d %s" % (len(bad), dict(Counter(r[2] for r in bad)) if bad else ""))
    print("orders delta : %d  (%d -> %d)" % (sold, orders_before, orders_after))
    print("order ids    : %s" % ids)
    print("stock after  : %s" % stock_after)
    print("cart items bought: %d  (this is the entire point: %d items -> %d orders)"
          % (cart_rows, cart_rows, sold))

    print("\n--- verdict ---")
    print("  stock arithmetic : %s" % ("CONSISTENT (no oversell)" if stock_after.split("/")[0] ==
                                        str(STOCK - sold) else "INCONSISTENT"))
    if sold > cart_rows:
        print("  RESULT: REPRODUCED -- %d orders were created from ONE cart that held %d item(s)."
              % (sold, cart_rows))
        print("          Missing idempotency guard: every concurrent request re-reads the same")
        print("          cart snapshot and each one writes its own order before any commit lands.")
    else:
        print("  RESULT: not reproduced this run (only %d order). Timing-dependent -- rerun."
              % sold)


if __name__ == "__main__":
    main()
