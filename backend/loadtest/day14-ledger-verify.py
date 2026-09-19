# -*- coding: utf-8 -*-
"""
Day 14 Step 4 -- inventory_logs ledger (three write points, three kinds of row).

Before this step, inventories was a table with no memory: it told you the CURRENT
split (available/locked/sold) but nothing about how it got there. inventory_logs
is the append-only book that records every single move.

The three write points, and what each one does to available_stock:

    ORDER_LOCK       deductStock       available - n , locked + n      (place order)
    PAY_SOLD         moveLockedToSold  locked - n    , sold + n        (pay)  <- available NOT touched
    CANCEL_RELEASE   releaseLocked     locked - n    , available + n   (cancel / timeout)

Decisions taken (Day 14 doc section 6):
  (1) before_stock / after_stock mean available_stock -- not total_stock.
      available is the only number a user can feel ("how many are left to buy"),
      and the only one inventory operations actually move.
  (2) the values come from PostgreSQL's UPDATE ... RETURNING, so "did it change"
      and "what did it become" arrive in ONE statement -- atomicity is preserved.
      (Validated separately by day14-returning-probe/run.sh, 17/17.)

What this script proves, in order of importance:

  * ★★ PAY_SOLD rows must have change_quantity == 0. This is not a gap in the
    data -- it IS the assertion. moveLockedToSold must not touch available_stock;
    if a PAY_SOLD row ever shows a non-zero change, the payment moved available,
    i.e. the same goods were deducted twice (the Day 13 disaster).
  * ★ ORDER_LOCK rows have reference_id = NULL. Not an oversight: createFromCart
    deducts stock (step 5) BEFORE inserting the order (step 6), so at that moment
    the order does not exist yet and there is no id to record.
  * ★ The ledger is a contiguous chain: each row's before_stock equals the
    previous row's after_stock. Nothing is missing, nothing is invented.
  * ★ The ledger can audit the present: available_now == available_at_start + Σ(change).
  * ★ A rejected order writes NO orphan row.

★ This script is RE-RUNNABLE: it snapshots the ledger's high-water mark and the
  starting available_stock, then only reasons about rows it created itself. It does
  not assume an empty table. (Artifacts it creates are reported, not deleted --
  Day 14 Step 5 does the reconciliation and cleanup.)

Usage:
    python day14-ledger-verify.py
Report (utf-8) is written next to this file: day14-ledger-verify-report.txt
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
OUT = os.path.join(HERE, "day14-ledger-verify-report.txt")

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


def delta(a, b):
    return "available %+d  locked %+d  sold %+d" % (
        b["available"] - a["available"], b["locked"] - a["locked"], b["sold"] - a["sold"])


def ledger(sku, after_id=0):
    """Ledger rows for a SKU with id > after_id, oldest first."""
    out = one("SELECT id||'|'||type||'|'||change_quantity||'|'||before_stock||'|'"
              "||after_stock||'|'||coalesce(reference_id::text,'NULL')||'|'"
              "||to_char(created_at,'HH24:MI:SS.MS')"
              " FROM inventory_logs WHERE sku_id=%d AND id>%d ORDER BY id" % (sku, after_id))
    rows = []
    for line in out.splitlines():
        p = [x.strip() for x in line.split("|")]
        if len(p) != 7:
            continue
        rows.append(dict(id=int(p[0]), type=p[1], change=int(p[2]), before=int(p[3]),
                         after=int(p[4]), ref=p[5], at=p[6]))
    return rows


def ledger_count():
    return int(one("SELECT count(*) FROM inventory_logs"))


def order_status(order_id):
    return one("SELECT status FROM orders WHERE id=%d" % order_id) or "(missing)"


def short(raw, n=200):
    raw = raw.replace("\r", "").replace("\n", " ").strip()
    return raw if len(raw) <= n else raw[:n] + " ...(truncated)"


def dump(tag, rows):
    say("  %s" % tag)
    say("    %-4s %-16s %8s %8s %8s %-8s %s"
        % ("id", "type", "change", "before", "after", "ref", "at"))
    for r in rows:
        say("    %-4d %-16s %+8d %8d %8d %-8s %s"
            % (r["id"], r["type"], r["change"], r["before"], r["after"], r["ref"], r["at"]))


# ================================================================ main
def main():
    checks = []

    def chk(name, good):
        checks.append((name, bool(good)))

    say("=" * 78)
    say("Day 14 Step 4 -- inventory_logs ledger (3 write points -> 3 kinds of row)")
    say("target : %s   account: demo(id=1)   sku under test: %d" % (BASE, TARGET_SKU))
    say("=" * 78)

    # ---------------------------------------------------------- [0] baseline
    say("\n[0] BASELINE (psql)")
    base = inv(TARGET_SKU)
    base_count = ledger_count()
    base_max_id = int(one("SELECT coalesce(max(id),0) FROM inventory_logs"))
    max_order_id = int(one("SELECT max(id) FROM orders"))
    A0 = base["available"]
    say(inv_line("stock", TARGET_SKU, base))
    say("  inventory_logs: rows=%d  high-water id=%d   max_order_id=%d"
        % (base_count, base_max_id, max_order_id))
    say("  ★ A0 = available_stock of sku%d at ledger start = %d" % (TARGET_SKU, A0))
    say("  ★ ledger-relative run: only rows with id > %d are judged below" % base_max_id)
    chk("baseline identity holds for sku%d" % TARGET_SKU, base["id_ok"])

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
        """Ensure sku x qty is in the cart, select it alone, create the order."""
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

    # ---------------------------------------------------------- [2] ORDER_LOCK
    say("\n[2] ORDER_LOCK -- place order A (sku%d x1)" % TARGET_SKU)
    order_a, code_a, _ = place_order()
    say("  POST /api/orders -> order=%s code=%s" % (order_a, code_a))
    chk("order A created", isinstance(order_a, int))
    if not isinstance(order_a, int):
        say("\nABORT: could not create order A")
        flush()
        return 1
    after_a = inv(TARGET_SKU)
    say(inv_line("after order A", TARGET_SKU, after_a))
    say("  delta: %s" % delta(base, after_a))
    chk("ordering moved available -1 / locked +1 / sold +0",
        after_a["available"] == A0 - 1
        and after_a["locked"] == base["locked"] + 1
        and after_a["sold"] == base["sold"])

    rows = ledger(TARGET_SKU, base_max_id)
    dump("new ledger rows:", rows)
    chk("exactly one new ledger row", len(rows) == 1)
    if rows:
        r = rows[0]
        chk("row type is ORDER_LOCK", r["type"] == "ORDER_LOCK")
        chk("ORDER_LOCK change is -1", r["change"] == -1)
        chk("ORDER_LOCK before == A0", r["before"] == A0)
        chk("ORDER_LOCK after == available now", r["after"] == after_a["available"])
        chk("ORDER_LOCK change == after - before", r["change"] == r["after"] - r["before"])
        chk("★ ORDER_LOCK reference_id is NULL (order not inserted yet)", r["ref"] == "NULL")

    # ---------------------------------------------------------- [3] PAY_SOLD
    say("\n[3] PAY_SOLD -- pay order A")
    st, b = pay(order_a)
    pd = b.get("data") or {}
    say("  POST /api/payments -> http=%s code=%s paymentId=%s" % (st, b.get("code"), pd.get("id")))
    chk("payment succeeded", st == 200 and b.get("code") == 200)
    after_pay = inv(TARGET_SKU)
    say(inv_line("after pay A", TARGET_SKU, after_pay))
    say("  delta vs after-order: %s   ★ available must NOT move" % delta(after_a, after_pay))
    chk("paying left available_stock untouched", after_pay["available"] == after_a["available"])
    chk("paying moved locked -1 / sold +1",
        after_pay["locked"] == after_a["locked"] - 1 and after_pay["sold"] == after_a["sold"] + 1)

    rows = ledger(TARGET_SKU, base_max_id)
    dump("new ledger rows:", rows)
    chk("ledger grew by exactly one row", len(rows) == 2)
    if len(rows) >= 2:
        r = rows[1]
        chk("second row type is PAY_SOLD", r["type"] == "PAY_SOLD")
        chk("★★ PAY_SOLD change == 0 (available must not move)", r["change"] == 0)
        chk("PAY_SOLD before == after", r["before"] == r["after"])
        chk("PAY_SOLD before/after == current available", r["after"] == after_pay["available"])
        chk("★ PAY_SOLD reference_id == order A", r["ref"] == str(order_a))

    # ---------------------------------------------------------- [4] ORDER_LOCK again
    say("\n[4] ORDER_LOCK again -- place order B (sku%d x1)" % TARGET_SKU)
    order_b, code_b, _ = place_order()
    say("  POST /api/orders -> order=%s code=%s" % (order_b, code_b))
    chk("order B created", isinstance(order_b, int))
    after_b = inv(TARGET_SKU)
    say(inv_line("after order B", TARGET_SKU, after_b))
    say("  delta vs after-pay: %s" % delta(after_pay, after_b))
    rows = ledger(TARGET_SKU, base_max_id)
    chk("ledger grew by exactly one row again", len(rows) == 3)
    if len(rows) >= 3:
        r = rows[2]
        chk("third row type is ORDER_LOCK", r["type"] == "ORDER_LOCK")
        chk("third row change is -1", r["change"] == -1)
        chk("third row reference_id is NULL", r["ref"] == "NULL")

    # ---------------------------------------------------------- [5] CANCEL_RELEASE
    say("\n[5] CANCEL_RELEASE -- cancel order B")
    st, b, _ = japi("POST", "/api/orders/%d/cancel" % order_b, token=demo)
    say("  POST /api/orders/%d/cancel -> http=%s code=%s" % (order_b, st, b.get("code")))
    chk("cancel succeeded", st == 200 and b.get("code") == 200)
    say("  order B status now = %s" % order_status(order_b))
    chk("order B is CANCELLED", order_status(order_b) == "CANCELLED")
    after_cancel = inv(TARGET_SKU)
    say(inv_line("after cancel B", TARGET_SKU, after_cancel))
    say("  delta vs after-order-B: %s" % delta(after_b, after_cancel))
    chk("cancelling moved available +1 / locked -1 / sold +0",
        after_cancel["available"] == after_b["available"] + 1
        and after_cancel["locked"] == after_b["locked"] - 1
        and after_cancel["sold"] == after_b["sold"])

    rows = ledger(TARGET_SKU, base_max_id)
    chk("ledger grew by exactly one row again (4 total)", len(rows) == 4)
    if len(rows) >= 4:
        r = rows[3]
        chk("fourth row type is CANCEL_RELEASE", r["type"] == "CANCEL_RELEASE")
        chk("CANCEL_RELEASE change is +1", r["change"] == 1)
        chk("CANCEL_RELEASE reference_id == order B", r["ref"] == str(order_b))

    # ---------------------------------------------------------- [6] full dump
    say("\n[6] FULL LEDGER CREATED BY THIS RUN (sku%d, oldest first)" % TARGET_SKU)
    dump("", rows)

    # ---------------------------------------------------------- [7] row invariants
    say("\n[7] ROW-LEVEL INVARIANTS (every row created by this run)")
    chk("every row satisfies change == after - before",
        all(r["change"] == r["after"] - r["before"] for r in rows))
    chk("every row has created_at (DB DEFAULT fired)", all(r["at"] for r in rows))
    chk("no row has a negative before/after",
        all(r["before"] >= 0 and r["after"] >= 0 for r in rows))
    chk("rows come back in id order (append-only)",
        [r["id"] for r in rows] == sorted(r["id"] for r in rows))

    # ---------------------------------------------------------- [8] type invariants
    say("\n[8] TYPE-LEVEL INVARIANTS")
    locks = [r for r in rows if r["type"] == "ORDER_LOCK"]
    pays = [r for r in rows if r["type"] == "PAY_SOLD"]
    rels = [r for r in rows if r["type"] == "CANCEL_RELEASE"]
    say("  ORDER_LOCK=%d  PAY_SOLD=%d  CANCEL_RELEASE=%d" % (len(locks), len(pays), len(rels)))
    chk("2 ORDER_LOCK rows", len(locks) == 2)
    chk("1 PAY_SOLD row", len(pays) == 1)
    chk("1 CANCEL_RELEASE row", len(rels) == 1)
    chk("★ every ORDER_LOCK change is negative", all(r["change"] < 0 for r in locks))
    chk("★ every ORDER_LOCK reference_id is NULL", all(r["ref"] == "NULL" for r in locks))
    chk("★★ every PAY_SOLD change is 0 (available untouched by payment)",
        all(r["change"] == 0 for r in pays))
    chk("★ every PAY_SOLD reference_id points at an order",
        all(r["ref"] != "NULL" for r in pays))
    chk("every CANCEL_RELEASE change is positive", all(r["change"] > 0 for r in rels))
    chk("every CANCEL_RELEASE reference_id points at an order",
        all(r["ref"] != "NULL" for r in rels))
    chk("sum of PAY_SOLD change is exactly 0", sum(r["change"] for r in pays) == 0)
    # ★ 不要写成「|Σ ORDER_LOCK| == Σ CANCEL_RELEASE」—— 那是错的：
    #   本轮的 A 单是【支付】掉的，它的锁定没被 release，而是变成 sold 了。
    #   正确的口径是：available 的全部位移只能由 ORDER_LOCK 与 CANCEL_RELEASE 解释，
    #   PAY_SOLD 对 available 的贡献恒为 0（这也正是上面那条断言的另一种说法）。
    lock_rel = sum(r["change"] for r in locks) + sum(r["change"] for r in rels)
    chk("★ available movement is fully explained by ORDER_LOCK + CANCEL_RELEASE"
        " (PAY_SOLD contributes 0)",
        lock_rel == after_cancel["available"] - A0)

    # ---------------------------------------------------------- [9] contiguity
    say("\n[9] LEDGER IS A CONTIGUOUS CHAIN (row[i].before == row[i-1].after)")
    breaks = [(rows[i - 1]["id"], rows[i - 1]["after"], rows[i]["id"], rows[i]["before"])
              for i in range(1, len(rows)) if rows[i]["before"] != rows[i - 1]["after"]]
    for prev_id, prev_after, cur_id, cur_before in breaks:
        say("  BREAK between #%d (after=%d) and #%d (before=%d)"
            % (prev_id, prev_after, cur_id, cur_before))
    chk("no gaps in the chain", not breaks)
    chk("chain starts at A0", bool(rows) and rows[0]["before"] == A0)
    chk("chain ends at current available",
        bool(rows) and rows[-1]["after"] == after_cancel["available"])

    # ---------------------------------------------------------- [10] audit
    say("\n[10] LEDGER AUDITS THE PRESENT:  available_now == A0 + Σ(change)")
    total_change = sum(r["change"] for r in rows)
    expected = A0 + total_change
    say("  A0 = %d   Σ(change) = %+d   A0 + Σ = %d   available now = %d"
        % (A0, total_change, expected, after_cancel["available"]))
    chk("★ ledger sum reproduces the current available_stock",
        expected == after_cancel["available"])

    # ---------------------------------------------------------- [11] orphan row
    say("\n[11] A REJECTED OPERATION MUST WRITE NO ORPHAN ROW")
    say("  ★ 两条被拒路径都不该往账本里留东西 —— 一条用户错误（重复取消），一条越权（IDOR）。")
    say("    （★ 说明边界：本步能观测到的是「被拒的操作不写流水」。更深一层的")
    say("     「UPDATE 成功但 INSERT 失败时一起回滚」在 API 上不可达 ——")
    say("     createFromCart 的第 3 步校验与 /api/cart 的两处库存校验把所有失败都挡在")
    say("     写流水之前；deductStock 的 0 行路径是纯竞态防线。该性质由 InventoryServiceImpl")
    say("     的 @Transactional 保证，属代码级论证，不在本脚本的断言范围内。）")

    st_i, b_i, _ = japi("POST", "/api/auth/login", body={"username": "intruder", "password": "intruder"})
    intr = (b_i.get("data") or {}).get("token")
    say("  intruder login -> http=%s code=%s token_len=%d" % (st_i, b_i.get("code"), len(intr or "")))
    chk("intruder login succeeded", bool(intr))

    before_orphan = ledger_count()
    st_d, b_d, raw_d = japi("POST", "/api/orders/%d/cancel" % order_b, token=demo)
    say("  demo double-cancel order B -> http=%s code=%s %s"
        % (st_d, b_d.get("code"), short(raw_d, 110)))
    chk("second cancel rejected", b_d.get("code") != 200)
    chk("rejection is a 400-class user error, not a 500", b_d.get("code") == 400)

    if intr:
        st_x, raw_x = api("POST", "/api/orders/%d/cancel" % order_b, token=intr)
        say("  intruder cancel demo's order B -> http=%s code=%s %s"
            % (st_x, body_code(raw_x), short(raw_x, 110)))
        chk("IDOR cancel rejected with business-404", body_code(raw_x) == 404)

    after_orphan = ledger_count()
    say("  ledger rows: %d -> %d" % (before_orphan, after_orphan))
    chk("★ no orphan ledger row after the rejected cancels", before_orphan == after_orphan)
    chk("stock untouched by the rejected cancels",
        inv(TARGET_SKU)["available"] == after_cancel["available"])
    chk("order B still CANCELLED", order_status(order_b) == "CANCELLED")

    # ---------------------------------------------------------- [12] final
    say("\n[12] FINAL STATE")
    final = inv(TARGET_SKU)
    say(inv_line("final", TARGET_SKU, final))
    chk("final identity holds", final["id_ok"])
    chk("no negative stock anywhere",
        int(one("SELECT count(*) FROM inventories WHERE available_stock < 0 OR locked_stock < 0"
                " OR sold_stock < 0")) == 0)
    drift = one("""
        WITH l AS (SELECT sku_id, locked_stock FROM inventories WHERE locked_stock <> 0),
             p AS (SELECT oi.sku_id, SUM(oi.quantity) q FROM order_items oi
                     JOIN orders o ON o.id = oi.order_id
                    WHERE o.status='PENDING_PAYMENT' GROUP BY oi.sku_id)
        SELECT count(*) FROM l FULL OUTER JOIN p ON l.sku_id = p.sku_id
         WHERE COALESCE(l.locked_stock,0) <> COALESCE(p.q,0)
    """)
    say("  business conservation (locked vs PENDING_PAYMENT items) drifting SKUs = %s" % drift)
    chk("business conservation holds (0 drifting SKUs)", drift.strip() == "0")
    say("  artifacts left behind (Step 5 reconciles + cleans):")
    say("    order #%s PAID, order #%s CANCELLED; sku%d sold +1"
        % (order_a, order_b, TARGET_SKU))

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
