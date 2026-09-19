# -*- coding: utf-8 -*-
"""
Day 12 Step 3: concurrent order load test.

Model: 20 INDEPENDENT users (lt1001..lt1020), each has its own cart + address,
all racing for the SAME 10 units of stock of sku_id=3.

Why independent users? createFromCart reads the *selected* cart rows of one user
and then CLEARS them. If 20 threads shared one account they would pile into the
same cart_items row (quantity accumulates to 20), so at most 1 order could ever
succeed -- the test could never observe the oversell boundary.

Evidence for "stock never went negative" comes from a DB trigger (lt_stock_audit,
created by loadtest-setup.sql) that records EVERY write to inventories, instead of
polling from Python -- polling via `docker exec` is far too slow to catch a 0.5s
race, and would only ever give a handful of samples.

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
THREADS = 20
USER_BASE = 1001          # lt1001 .. lt1020
ADDR_OFFSET = 1000        # addressId = 1000 + userId  (fixed mapping from setup SQL)
PASSWORD = "loadtest123"

SKU_ID = 3
BUY_QTY = 1
EXPECT_STOCK = 10

DOCKER = r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ---------------------------------------------------------------- http helper
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


# ---------------------------------------------------------------- db helper
def psql(sql):
    p = subprocess.run(
        [DOCKER, "exec", "-i", "-e", "PGCLIENTENCODING=UTF8",
         "mallx-postgres", "psql", "-U", "mallx", "-d", "mallx",
         "-t", "-A", "-F", "|", "-c", sql],
        capture_output=True)
    return p.stdout.decode("utf-8", "replace").strip()


def stock_row():
    out = psql("SELECT total_stock, available_stock, locked_stock, sold_stock, "
               "(total_stock = available_stock + locked_stock + sold_stock) "
               "FROM inventories WHERE sku_id = " + str(SKU_ID))
    parts = out.split("|")
    if len(parts) < 5:
        raise RuntimeError("bad stock row: " + out)
    return dict(total=int(parts[0]), available=int(parts[1]),
                locked=int(parts[2]), sold=int(parts[3]), identity_ok=(parts[4] == "t"))


def audit_rows():
    """Every UPDATE ever applied to inventories (sku 3), in order."""
    out = psql("SELECT available, locked, sold FROM lt_stock_audit ORDER BY id")
    rows = []
    for line in out.splitlines():
        p = line.split("|")
        if len(p) == 3:
            try:
                rows.append((int(p[0]), int(p[1]), int(p[2])))
            except ValueError:
                pass
    return rows


# ---------------------------------------------------------------- workers
results = []
rlock = threading.Lock()
barrier = threading.Barrier(THREADS)


def worker(uid):
    uname = "lt" + str(uid)
    rec = {"uid": uid, "login": None, "add": None, "order": None}

    st, body = api("POST", "/api/auth/login", body={"username": uname, "password": PASSWORD})
    token = (body.get("data") or {}).get("token")
    rec["login"] = (st, body.get("code"))

    if token:
        st, body = api("POST", "/api/cart", token=token,
                       body={"skuId": SKU_ID, "quantity": BUY_QTY})
        rec["add"] = (st, body.get("code"))

    # ---- sync point: all threads fire POST /api/orders at (almost) the same instant
    barrier.wait()

    if token:
        st, body = api("POST", "/api/orders", token=token,
                       body={"addressId": ADDR_OFFSET + uid})
        # NOTE: POST /api/orders returns Result<Long> -- data is the ORDER ID (an int),
        # NOT an OrderVO object. Do not call .get() on it.
        data = body.get("data")
        if isinstance(data, dict):
            order_no, order_id = data.get("orderNo"), data.get("id")
        else:
            order_no, order_id = None, data
        rec["order"] = (st, body.get("code"), body.get("message"), order_no, order_id)

    with rlock:
        results.append(rec)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "conditional"
    orders_before = int(psql("SELECT count(*) FROM orders"))
    st_before = stock_row()

    print("=" * 68)
    print("Day 12 Step 3 -- concurrent order load test")
    print("mode         :", mode)
    print("target       :", BASE)
    print("threads      :", THREADS, " independent users, each buys %d x sku %d" % (BUY_QTY, SKU_ID))
    print("stock before : total=%d available=%d locked=%d sold=%d" % (
        st_before["total"], st_before["available"], st_before["locked"], st_before["sold"]))
    print("orders before:", orders_before)

    t0 = time.time()
    workers = [threading.Thread(target=worker, args=(USER_BASE + i,)) for i in range(THREADS)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    elapsed = time.time() - t0

    # ------------------------------------------------------------ per-thread
    print("\n--- per-thread (elapsed %.2fs) ---" % elapsed)
    for r in sorted(results, key=lambda x: x["uid"]):
        o = r["order"]
        line = "  uid=%d login=%s add=%s" % (r["uid"], r["login"], r["add"])
        if o:
            line += "  order http=%s code=%s" % (o[0], o[1])
            if o[1] == 200:
                line += " orderId=%s" % o[4]
            elif o[2]:
                line += " msg=%s" % o[2]
        print(line)

    # ------------------------------------------------------------ summary
    ok = [r for r in results if r["order"] and r["order"][1] == 200]
    bad = [r for r in results if not r["order"] or r["order"][1] != 200]
    codes = Counter((r["order"][1] if r["order"] else "no-call") for r in bad)
    msgs = Counter((r["order"][2] if r["order"] else "login/add failed") for r in bad)

    orders_after = int(psql("SELECT count(*) FROM orders"))
    st_after = stock_row()
    distinct_no = psql("SELECT count(*) || '/' || count(DISTINCT order_no) FROM orders")
    audit = audit_rows()
    avs = [a for a, _, _ in audit]

    print("\n--- summary ---")
    print("success       : %d" % len(ok))
    print("failed        : %d" % len(bad))
    print("fail codes    : %s" % dict(codes))
    print("fail messages : %s" % dict(msgs))
    print("orders delta  : %d  (%d -> %d)" % (orders_after - orders_before, orders_before, orders_after))
    print("order_no uniq : %s (count/distinct)" % distinct_no)
    print("stock after   : total=%d available=%d locked=%d sold=%d identity_ok=%s" % (
        st_after["total"], st_after["available"], st_after["locked"], st_after["sold"],
        st_after["identity_ok"]))

    print("\n--- stock audit: EVERY write to inventories (sku %d), recorded by DB trigger ---" % SKU_ID)
    if not audit:
        print("  (no rows -- was the trigger created by loadtest-setup.sql?)")
    for i, (a, l, s) in enumerate(audit, 1):
        print("  #%02d  available=%2d  locked=%2d  sold=%d" % (i, a, l, s))

    # ------------------------------------------------------------ assertions
    sold_qty = sum(BUY_QTY for _ in ok)
    monotonic = all(avs[i] > avs[i + 1] for i in range(len(avs) - 1)) if len(avs) > 1 else False
    checks = [
        ("DB audit captured every deduction (%d writes)" % EXPECT_STOCK, len(audit) == EXPECT_STOCK),
        ("no negative stock in ANY recorded write", bool(avs) and min(avs) >= 0),
        ("available strictly decreasing 10 -> 0", monotonic and avs[0] == st_before["available"] - 1
         and avs[-1] == 0),
        ("success count == shared stock (%d)" % EXPECT_STOCK, len(ok) == EXPECT_STOCK),
        ("failed count == threads - stock", len(bad) == THREADS - EXPECT_STOCK),
        ("all failures are HTTP 200 + code 400", all(r["order"] and r["order"][0] == 200
                                                      and r["order"][1] == 400 for r in bad)),
        ("available == before - sold_qty", st_after["available"] == st_before["available"] - sold_qty),
        ("locked == before + sold_qty", st_after["locked"] == st_before["locked"] + sold_qty),
        ("total = available + locked + sold", st_after["identity_ok"]),
        ("orders delta == success count", orders_after - orders_before == len(ok)),
        ("all order_no unique", distinct_no.split("/")[0] == distinct_no.split("/")[1]),
        ("NO OVERSELL: orders_created <= stock", (orders_after - orders_before) <= EXPECT_STOCK),
    ]

    print("\n--- assertions ---")
    passed = 0
    for name, good in checks:
        print("  [%s] %s" % ("PASS" if good else "FAIL", name))
        passed += 1 if good else 0
    print("\nRESULT: %d/%d passed" % (passed, len(checks)))
    print("VERDICT:", "NO OVERSELL" if passed == len(checks) else "OVERSELL / PROBLEM DETECTED")


if __name__ == "__main__":
    main()
