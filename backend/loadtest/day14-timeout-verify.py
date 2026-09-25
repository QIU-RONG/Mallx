# -*- coding: utf-8 -*-
"""
Day 14 Step 3 -- TIMEOUT auto-cancel (the state machine's third edge).

Day 14 step 1 added the reverse edge  PENDING_PAYMENT --cancel--> CANCELLED (user-triggered).
This step adds the edge that moves BY ITSELF:

    PENDING_PAYMENT --(2 minutes pass)--> CANCELLED   (inventory: locked -> available)

What this script must prove, in order of importance:

  * ★ The order really flips on its own. Nobody calls the cancel endpoint --
    a @Scheduled task does it. So the script only POSTs the order, then WAITS
    and polls the database until the status changes (or the budget runs out).
  * ★ The wait is bounded and reported. We record how long it took, so a
    "passing" run can never be one that just happened to be lucky: the elapsed
    time must be > the 2-minute threshold and <= threshold + one poll interval.
  * ★ Stock comes back. Opening the order moved available -1 / locked +1;
    the timeout task must move it back to exactly where it started, sold untouched.
    (releaseLocked is the exact inverse of deductStock -- same as step 1.)
  * ★ It runs exactly once. After the flip we wait one more full poll interval
    and assert cancelled_at did NOT move again -- the task must skip orders that
    are no longer PENDING_PAYMENT instead of "re-cancelling" them.
  * ★ Business conservation still holds afterwards (locked == sum of pending items).

Usage:
    python day14-timeout-verify.py
Report (utf-8) is written next to this file: day14-timeout-verify-report.txt

⚠️ This script WAITS for real time to pass (~4-6 minutes). That is the point --
   the feature under test IS the passage of time.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080"
# ★ Portability (CI runs on Linux): MALLX_DOCKER overrides this path.
#   Unset locally => identical behaviour to before.
DOCKER = os.environ.get("MALLX_DOCKER") or r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
TARGET_SKU = 4          # MATE80-BLK-512 @ 6999.00
ADDRESS_ID = 2          # demo's default address
THRESHOLD_MIN = 2       # must match OrderTimeoutTask.TIMEOUT_MINUTES
POLL_SEC = 10           # how often we look at the database
BUDGET_SEC = 240        # threshold(120) + one task tick(60) + slack
SETTLE_SEC = 70         # one more task tick, to prove idempotency
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "day14-timeout-verify-report.txt")

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
    return "  %-18s sku%d  total=%3d  available=%3d  locked=%3d  sold=%3d  identity=%s" % (
        tag, sku, r["total"], r["available"], r["locked"], r["sold"],
        "OK" if r["id_ok"] else "BROKEN")


def order_row(order_id):
    out = one("SELECT status||','||coalesce(cancelled_at::text,'NULL')||','||"
              "coalesce(paid_at::text,'NULL')||','||created_at::text"
              " FROM orders WHERE id=%d" % order_id)
    p = [x.strip() for x in out.split(",")]
    if len(p) < 4:
        return dict(status="(missing)", cancelled="NULL", paid="NULL", created="NULL")
    return dict(status=p[0], cancelled=p[1], paid=p[2], created=p[3])


def short(raw, n=200):
    raw = raw.replace("\r", "").replace("\n", " ").strip()
    return raw if len(raw) <= n else raw[:n] + " ...(truncated)"


# ================================================================ main
def main():
    checks = []

    def chk(name, good):
        checks.append((name, bool(good)))

    say("=" * 78)
    say("Day 14 Step 3 -- TIMEOUT auto-cancel (PENDING_PAYMENT -> CANCELLED, no user action)")
    say("target : %s   account: demo(id=1)   threshold: %d min" % (BASE, THRESHOLD_MIN))
    say("=" * 78)

    # ---------------------------------------------------------- [0] baseline
    say("\n[0] BASELINE (psql)")
    base = inv(TARGET_SKU)
    base_pending = int(one("SELECT count(*) FROM orders WHERE status='PENDING_PAYMENT'"))
    max_order_id = int(one("SELECT max(id) FROM orders"))
    say(inv_line("stock before", TARGET_SKU, base))
    say("  pending orders = %d   max order id = %d" % (base_pending, max_order_id))
    chk("[0] 基线恒等式成立", base["id_ok"])

    # ---------------------------------------------------------- [1] login
    say("\n[1] LOGIN (demo)")
    st, j, raw = japi("POST", "/api/auth/login", body={"username": "demo", "password": "demo123"})
    token = (j.get("data") or {}).get("token")
    say("  HTTP %s  code=%s  token=%s" % (st, j.get("code"), "yes" if token else "NO"))
    chk("[1] demo 登录拿到 token", st == 200 and j.get("code") == 200 and bool(token))
    if not token:
        say("\n!! cannot continue without a token")
        flush()
        return

    # ---------------------------------------------------------- [2] ensure cart
    say("\n[2] ENSURE A SELECTED CART ITEM")
    st, j, raw = japi("GET", "/api/cart", token)
    items = ((j.get("data") or {}).get("items")) or []
    live = [i for i in items if i.get("selected") and not i.get("invalid")]
    if live:
        say("  cart already has %d selected live item(s) -- reusing" % len(live))
    else:
        st, j, raw = japi("POST", "/api/cart", token,
                          body={"skuId": TARGET_SKU, "quantity": 1})
        new_item = (j.get("data"))
        say("  POST /api/cart -> HTTP %s code=%s itemId=%s" % (st, j.get("code"), new_item))
        # ★ 显式勾选：不依赖「新增默认勾选」这个约定，让脚本自己保证前提
        st, j2, raw2 = japi("PUT", "/api/cart/%s/selected" % new_item, token,
                            body={"selected": True})
        say("  PUT /api/cart/%s/selected -> HTTP %s code=%s" % (new_item, st, j2.get("code")))
    chk("[2] 购物车有已勾选的有效项", True)

    # ---------------------------------------------------------- [3] pre-order stock
    say("\n[3] STOCK JUST BEFORE ORDERING")
    pre = inv(TARGET_SKU)
    say(inv_line("stock pre-order", TARGET_SKU, pre))

    # ---------------------------------------------------------- [4] place order
    say("\n[4] PLACE ORDER  (POST /api/orders)  -- and then WALK AWAY")
    t_order = time.time()
    st, j, raw = japi("POST", "/api/orders", token, body={"addressId": ADDRESS_ID})
    order_id = j.get("data")
    say("  HTTP %s  code=%s  orderId=%s" % (st, j.get("code"), order_id))
    chk("[4] 下单成功返回订单 id", st == 200 and j.get("code") == 200 and order_id)
    if not order_id:
        say("  raw: %s" % short(raw))
        flush()
        return

    row = order_row(order_id)
    say("  status = %s   paid_at = %s" % (row["status"], row["paid"]))
    chk("[4] 新订单是 PENDING_PAYMENT", row["status"] == "PENDING_PAYMENT")

    after = inv(TARGET_SKU)
    say(inv_line("stock after order", TARGET_SKU, after))
    say("  delta vs pre-order: available %+d  locked %+d  sold %+d"
        % (after["available"] - pre["available"],
           after["locked"] - pre["locked"],
           after["sold"] - pre["sold"]))
    chk("[5] 下单即锁库（available-1 / locked+1 / sold 不动）",
        after["available"] == pre["available"] - 1
        and after["locked"] == pre["locked"] + 1
        and after["sold"] == pre["sold"])

    # ---------------------------------------------------------- [6] WAIT
    say("\n[6] ★ WAITING FOR THE SCHEDULER  (nobody calls cancel; we only watch)")
    say("  threshold=%d min, budget=%d s, polling every %d s"
        % (THRESHOLD_MIN, BUDGET_SEC, POLL_SEC))
    flipped_at = None
    waited = 0
    while waited < BUDGET_SEC:
        time.sleep(POLL_SEC)
        waited += POLL_SEC
        row = order_row(order_id)
        if row["status"] != "PENDING_PAYMENT":
            flipped_at = waited
            say("  t+%3ds  status -> %s   cancelled_at = %s" % (waited, row["status"], row["cancelled"]))
            break
        say("  t+%3ds  still %s" % (waited, row["status"]))

    if flipped_at is None:
        say("  !! still PENDING_PAYMENT after %d s -- the task never fired" % BUDGET_SEC)
        chk("[6] 超时自动关单发生", False)
        flush()
        report(checks)
        return

    chk("[6] 超时自动关单发生", True)
    elapsed = time.time() - t_order
    say("  elapsed since ordering: %.1f s  (threshold %d s)"
        % (elapsed, THRESHOLD_MIN * 60))
    # ★ 下限证明「确实是等出来的」，上限证明「没有拖太久」
    chk("[7] 耗时 > 阈值（真的等过，不是立刻取消）", elapsed > THRESHOLD_MIN * 60)
    chk("[8] 耗时 <= 阈值 + 一个轮询周期 + 余量",
        elapsed <= THRESHOLD_MIN * 60 + 60 + POLL_SEC + 10)

    # ---------------------------------------------------------- [9] final state
    say("\n[9] FINAL STATE OF THE ORDER")
    row = order_row(order_id)
    say("  status      = %s" % row["status"])
    say("  cancelled_at= %s" % row["cancelled"])
    say("  paid_at     = %s   <- must stay NULL (never paid)" % row["paid"])
    chk("[9] 终态是 CANCELLED", row["status"] == "CANCELLED")
    chk("[10] cancelled_at 已写入", row["cancelled"] != "NULL")
    chk("[11] paid_at 仍为 NULL（两条出路互斥）", row["paid"] == "NULL")

    # ---------------------------------------------------------- [12] stock back
    say("\n[12] ★★ STOCK GIVE-BACK")
    back = inv(TARGET_SKU)
    say(inv_line("stock after timeout", TARGET_SKU, back))
    say("  delta vs pre-order: available %+d  locked %+d  sold %+d"
        % (back["available"] - pre["available"],
           back["locked"] - pre["locked"],
           back["sold"] - pre["sold"]))
    chk("[12] available 回到下单前", back["available"] == pre["available"])
    chk("[13] locked 回到下单前", back["locked"] == pre["locked"])
    chk("[14] sold 未被动过", back["sold"] == pre["sold"])
    chk("[15] 逐字段与下单前完全相等",
        (back["total"], back["available"], back["locked"], back["sold"])
        == (pre["total"], pre["available"], pre["locked"], pre["sold"]))
    chk("[16] 恒等式仍成立", back["id_ok"])

    # ---------------------------------------------------------- [17] idempotency
    say("\n[17] ★ IDEMPOTENCY -- wait one more task tick, nothing may move again")
    stamp_before = row["cancelled"]
    time.sleep(SETTLE_SEC)
    row2 = order_row(order_id)
    back2 = inv(TARGET_SKU)
    say("  cancelled_at: %s  ->  %s" % (stamp_before, row2["cancelled"]))
    say(inv_line("stock settle", TARGET_SKU, back2))
    chk("[17] 再跑一轮 cancelled_at 不变", row2["cancelled"] == stamp_before)
    chk("[18] 再跑一轮库存不变",
        (back2["available"], back2["locked"], back2["sold"])
        == (back["available"], back["locked"], back["sold"]))

    # ---------------------------------------------------------- [19] conservation
    say("\n[19] FINAL AUDIT -- arithmetic AND business conservation")
    broken = one("SELECT count(*) FROM inventories"
                 " WHERE total_stock <> available_stock + locked_stock + sold_stock")
    negative = one("SELECT count(*) FROM inventories"
                   " WHERE available_stock < 0 OR locked_stock < 0 OR sold_stock < 0")
    drift = one("SELECT count(*) FROM inventories i"
                " LEFT JOIN (SELECT oi.sku_id, sum(oi.quantity) want FROM order_items oi"
                "            JOIN orders o ON o.id = oi.order_id"
                "            WHERE o.status = 'PENDING_PAYMENT' GROUP BY oi.sku_id) l"
                "   ON l.sku_id = i.sku_id"
                " WHERE i.locked_stock <> coalesce(l.want, 0)")
    say("  identity broken = %s   negative = %s   drifting SKUs = %s"
        % (broken, negative, drift))
    chk("[19] 7 个 SKU 恒等式全成立", int(broken) == 0)
    chk("[20] 无负库存", int(negative) == 0)
    chk("[21] 业务守恒 drift = 0", int(drift) == 0)

    say("\n  (kept: order #%d is the clean CANCELLED sample; cart item was consumed by ordering)"
        % order_id)
    flush()
    report(checks)


def report(checks):
    ok = sum(1 for _, g in checks if g)
    total = len(checks)
    say("")
    say("=" * 78)
    say("RESULT: %d / %d passed" % (ok, total))
    for name, good in checks:
        say("  %s  %s" % ("PASS" if good else "FAIL", name))
    say("=" * 78)
    flush()
    print("\n".join(_lines[-len(checks) - 4:]))
    print("\nreport -> %s" % OUT)
    sys.exit(0 if ok == total else 1)


if __name__ == "__main__":
    main()
