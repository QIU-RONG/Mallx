# -*- coding: utf-8 -*-
"""Day 26 · M1 回归夹具 —— 让 245/245 第一次可以【从零复现】

为什么需要这个脚本（CI 本地等价验证的真实发现，2026-09-25）
----------------------------------------------------------
把 01→14 的全新 initdb 库 + 新起的应用直接跑 M1，得到的是 44/72，而不是 245/245。
根因不是一个 bug，而是三个【从未被写下来的隐藏前置】——它们在 dev 库里
从来都是「Day 12/13/14 手工测试的残留」，所以 25 天里没人看见：

  1. `users` 表只有 demo(id=1)，没有 intruder —— day15 的入侵者断言、
     day17-b 的「非属主伪装 404」断言都要 intruder/intruder 能登录；
  2. `user_addresses` 表是空的 —— day14/15/16 硬编码 ADDRESS_ID=2，下单必败
     （day14 实测 [FAIL] PATH A: order A created）；
  3. `orders` 表是空的 —— day17-a/b 是【读侧】断言，读的是别人的订单；
     链路脚本 day14/15/16 全部自清洁，跑完一张订单都不剩。

修法（为什么走 API 而不是纯 SQL）
--------------------------------
地址 / 用户用 SQL（id 是承重墙：脚本硬编码 id=1/2，走 06-fixtures 的显式 id 惯例，
插完校准序列 —— REF §四）；订单走【真实业务路径】（购物车 → 下单 → 支付 → 发货 →
确认），一致性由应用自己保证，SQL 里手写订单/支付/库存/流水四张表的对账关系
才是真正的脆弱点。

幂等协议
--------
状态文件 `day26-m1-fixture-state.json` 记录本轮创建的订单 id。再次运行时：
  * 状态文件在 且 所有订单还在且状态相符 → no-op（NOTICE），退出 0；
  * 否则（全新库 / 状态文件丢失）→ 重新创建。
夹具订单【不清理】——它们进入 M1 收集器的 baseline（先 apply 后 --baseline），
这与 dev 库 25 天来的实际形态一致：总有一批历史订单躺在那里被读侧脚本读。

用法
----
    python day26-m1-fixture.py             # apply（幂等）
    python day26-m1-fixture.py --status    # 只读盘点，不写

前置：应用已在 127.0.0.1:8080 就绪；postgres 容器 mallx-postgres 在跑；
01→14（含 06 管理端夹具）已初始化。CI 里排在 baseline 之前（见 .github/workflows/ci.yml）。
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8080"
DOCKER = os.environ.get("MALLX_DOCKER") or \
    r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
CONTAINER = "mallx-postgres"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "day26-m1-fixture-report.txt")
STATE = os.path.join(HERE, "day26-m1-fixture-state.json")

DEMO_ADDRESS_ID = 2          # day14/15/16 硬编码，承重墙，不许改
INTRUDER_ID = 2              # day15/day17-b 的「非属主」账号

# 订单形态由链路脚本的四个【绝对判定】倒推（不是随便选的）：
#   * day17-a 分页断言要 page1/page2 各满 3 行  → 至少 6 单；
#   * day14 基线要求无 PENDING_PAYMENT 且 locked 全 0 → 不能留挂起单；
#   * day15/16 清理后要求全库 0 张 SHIPPED/COMPLETED → 不能用这两个状态；
#     ⇒ 六张全部 PAID。
#   * dev 库的历史形态（git 里 Day 24 的报告）正是「8 单全 PAID 系 / 0 流水」。
PLAN = [
    {"sku": 1, "qty": 1, "target": "PAID"},
    {"sku": 4, "qty": 1, "target": "PAID"},
    {"sku": 2, "qty": 2, "target": "PAID"},
    {"sku": 3, "qty": 1, "target": "PAID"},
    {"sku": 5, "qty": 1, "target": "PAID"},
    {"sku": 6, "qty": 1, "target": "PAID"},
]

_lines = []


def say(s=""):
    _lines.append(s)


def flush():
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(_lines) + "\n")
    print("\n".join(_lines[-6:]))


# ---------------------------------------------------------------- http helper
def api(method, path, token=None, body=None, timeout=30):
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
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", "replace"))
        except ValueError:
            return e.code, {"raw": "?"}
    except Exception as e:                                            # noqa: BLE001
        return -1, {"transport_error": repr(e)}


# ---------------------------------------------------------------- db helper
def psql(sql):
    p = subprocess.run(
        [DOCKER, "exec", "-i", "-e", "PGCLIENTENCODING=UTF8",
         CONTAINER, "psql", "-U", "mallx", "-d", "mallx",
         "-t", "-A", "-F", "|", "-c", sql],
        capture_output=True)
    out = p.stdout.decode("utf-8", "replace").strip()
    err = p.stderr.decode("utf-8", "replace").strip()
    if p.returncode != 0 or "ERROR" in err:
        raise RuntimeError("psql failed (rc=%d)\nSQL: %s\nstderr: %s" % (p.returncode, sql, err))
    return out


def one(sql):
    return psql(sql).strip()


# ---------------------------------------------------------------- fixtures
def ensure_intruder():
    """intruder/id=2。缺了插入；id=2 被别人占 → ABORT（id 是承重墙）。"""
    row = one("SELECT id FROM users WHERE username='intruder';")
    if row:
        say("  intruder 已存在 id=%s" % row)
        if int(row) != INTRUDER_ID:
            say("  ★ ABORT: intruder 的 id=%s ≠ %d —— day15/day17-b 的描述以 id=2 为前提" % (row, INTRUDER_ID))
            return False
        return True
    one("INSERT INTO users (id, username, password, nickname, phone, email, status) "
        "VALUES (%d, 'intruder', '{noop}intruder', '入侵者(夹具)', '13800000002', "
        "'intruder@mallx.local', 1);" % INTRUDER_ID)
    one("SELECT setval(pg_get_serial_sequence('users','id'), (SELECT max(id) FROM users));")
    got = one("SELECT id FROM users WHERE username='intruder';")
    ok = got == str(INTRUDER_ID)
    say("  intruder 插入 -> id=%s %s" % (got, "OK" if ok else "MISMATCH"))
    return ok


def ensure_address():
    """demo 的收货地址，显式 id=2（day14/15/16 硬编码，属主必须是 user_id=1）。"""
    row = one("SELECT user_id FROM user_addresses WHERE id=%d;" % DEMO_ADDRESS_ID)
    if row:
        if int(row) != 1:
            say("  ★ ABORT: 地址 id=%d 的属主是 user_id=%s ≠ 1" % (DEMO_ADDRESS_ID, row))
            return False
        say("  地址 id=%d 已存在（属主 demo）" % DEMO_ADDRESS_ID)
        return True
    cnt = one("SELECT count(*) FROM user_addresses;")
    if cnt != "0":
        say("  ★ ABORT: 地址表非空(%s 行)却缺 id=%d —— 显式插入有撞车风险，请人工确认"
            % (cnt, DEMO_ADDRESS_ID))
        return False
    one("INSERT INTO user_addresses (id, user_id, receiver_name, receiver_phone, "
        "province, city, district, detail_address, is_default) "
        "VALUES (%d, 1, '演示收货人', '13800000001', '浙江省', '杭州市', '西湖区', "
        "'文三路 100 号（夹具）', TRUE);" % DEMO_ADDRESS_ID)
    one("SELECT setval(pg_get_serial_sequence('user_addresses','id'), "
        "(SELECT max(id) FROM user_addresses));")
    got = one("SELECT user_id FROM user_addresses WHERE id=%d;" % DEMO_ADDRESS_ID)
    ok = got == "1"
    say("  地址插入 -> id=%d user_id=%s %s" % (DEMO_ADDRESS_ID, got, "OK" if ok else "MISMATCH"))
    return ok


def login(path, username, password):
    st, b = api("POST", path, body={"username": username, "password": password})
    tok = (b.get("data") or {}).get("token") if isinstance(b.get("data"), dict) else None
    return tok, (b.get("code"), len(tok or ""))


def cart_flow(demo, admin, plan, checks):
    """加购(或复用残留行) → 独选 → 下单 → 按目标状态推进。

    ★ 购物车不在任何脚本的清理模型里：失败重跑常留下旧行，POST 再加同一 sku
      会被业务拒绝 —— 所以必须先 GET 复用，不能盲目 POST。
    """
    created = []
    for p in plan:
        st, b = api("GET", "/api/cart", token=demo)
        items = (b.get("data") or {}).get("items") if isinstance(b.get("data"), dict) \
            else b.get("data")
        items = items or []
        it = next((x for x in items if x.get("skuId") == p["sku"]), None)
        if it is None:
            st, b = api("POST", "/api/cart", token=demo,
                        body={"skuId": p["sku"], "quantity": p["qty"]})
            if st != 200 or b.get("code") != 200:
                msg = (b.get("message") or b.get("msg") or b.get("raw") or "?")
                say("  [FAIL] 加购 sku%d: http=%s code=%s msg=%s" % (p["sku"], st, b.get("code"), msg))
                checks.append(("cart add sku%d" % p["sku"], False))
                return created
            st, b = api("GET", "/api/cart", token=demo)
            items = (b.get("data") or {}).get("items") if isinstance(b.get("data"), dict) \
                else b.get("data")
            items = items or []
            it = next((x for x in items if x.get("skuId") == p["sku"]), None)
        if it is None:
            say("  [FAIL] 购物车里找不到 sku%d" % p["sku"])
            checks.append(("cart find sku%d" % p["sku"], False))
            return created
        api("PUT", "/api/cart/%s" % it["id"], token=demo, body={"quantity": p["qty"]})
        for x in items:                                   # 独选：只选当前 sku 的行
            api("PUT", "/api/cart/%s/selected" % x["id"], token=demo,
                body={"selected": x["id"] == it["id"]})
        st, b = api("POST", "/api/orders", token=demo, body={"addressId": DEMO_ADDRESS_ID})
        oid = b.get("data") if st == 200 and isinstance(b.get("data"), int) else None
        checks.append(("place order sku%d -> id=%s" % (p["sku"], oid),
                       oid is not None and b.get("code") == 200))
        if oid is None:
            return created
        oid = int(oid)

        if p["target"] != "PENDING_PAYMENT":
            st, b = api("POST", "/api/payments", token=demo,
                        body={"orderId": oid, "method": "ALIPAY"})
            checks.append(("pay order%d -> PAID" % oid, st == 200 and b.get("code") == 200))
            if p["target"] in ("SHIPPED", "COMPLETED"):
                st, b = api("POST", "/api/orders/%d/ship" % oid, token=admin)
                checks.append(("ship order%d -> SHIPPED" % oid, st == 200 and b.get("code") == 200))
            if p["target"] == "COMPLETED":
                st, b = api("POST", "/api/orders/%d/confirm" % oid, token=demo)
                checks.append(("confirm order%d -> COMPLETED" % oid, st == 200 and b.get("code") == 200))

        got = one("SELECT status FROM orders WHERE id=%d;" % oid)
        checks.append(("order%d status=%s" % (oid, p["target"]), got == p["target"]))
        created.append({"id": oid, "sku": p["sku"], "qty": p["qty"], "target": p["target"]})
    return created


def identity_ok(sku):
    row = one("SELECT total_stock, available_stock, locked_stock, sold_stock "
              "FROM inventories WHERE sku_id=%d;" % sku).split("|")
    t, a, l, s = map(int, row)
    return t == a + l + s, (t, a, l, s)


# ---------------------------------------------------------------- main
def main():
    status_only = "--status" in sys.argv
    say("=" * 78)
    say("Day 26 -- M1 回归夹具（让 245/245 可以从零复现）")
    say("target : %s   plan: %s" % (BASE, ", ".join("sku%d x%d->%s" % (p["sku"], p["qty"], p["target"]) for p in PLAN)))
    say("=" * 78)

    st, b = api("GET", "/api/hello")
    if st != 200:
        say("★ ABORT: 应用未就绪（/api/hello http=%s）—— 先起应用再跑夹具" % st)
        flush()
        return 1
    say("[0] 应用就绪")

    # 幂等检查（--status 也走这一段）
    if os.path.exists(STATE):
        try:
            prev = json.load(open(STATE, encoding="utf-8"))
        except ValueError:
            prev = None
        if prev and prev.get("orders"):
            ids = ",".join(str(o["id"]) for o in prev["orders"])
            present = one("SELECT count(*) FROM orders WHERE id IN (%s);" % ids)
            if present == str(len(prev["orders"])):
                say("[1] 夹具已在位（状态文件 %d 单全部存在）→ no-op" % len(prev["orders"]))
                say("    订单: %s" % ids)
                flush()
                return 0
            say("[1] 状态文件在但订单缺（present=%s/%d）→ 重建"
                % (present, len(prev["orders"])))

    if status_only:
        say("[--status] 无有效夹具状态（新库跑 apply 即可）")
        flush()
        return 0

    checks = []
    say("[1] SQL 夹具（显式 id 惯例，插后校准序列）")
    if not ensure_intruder():
        flush()
        return 1
    checks.append(("intruder user (id=%d) in place" % INTRUDER_ID,
                   one("SELECT count(*) FROM users WHERE username='intruder';") == "1"))
    if not ensure_address():
        flush()
        return 1
    checks.append(("demo address (id=%d) in place" % DEMO_ADDRESS_ID,
                   one("SELECT count(*) FROM user_addresses WHERE id=%d AND user_id=1;"
                       % DEMO_ADDRESS_ID) == "1"))

    say("[2] 登录")
    demo, m1 = login("/api/auth/login", "demo", "demo123")
    admin, m2 = login("/api/auth/admin/login", "admin", "admin123")
    say("    demo token_len=%s (code=%s)   admin token_len=%s (code=%s)"
        % (m1[1], m1[0], m2[1], m2[0]))
    checks.append(("demo login", bool(demo)))
    checks.append(("admin login", bool(admin)))
    if not demo or not admin:
        flush()
        return 1

    say("[3] 归零幽灵计数（种子自带 sold/locked 残数且无订单可解释，违反链路守恒前提）")
    one("UPDATE inventories SET locked_stock = 0, sold_stock = 0, "
        "available_stock = total_stock, updated_at = CURRENT_TIMESTAMP;")
    say("    locked/sold 全表归零，available=total")

    say("[4] API 建单（真实业务路径：购物车 → 下单 → 支付）")
    created = cart_flow(demo, admin, PLAN, checks)
    say("    创建 %d 单: %s" % (len(created),
        ", ".join("#%d sku%d->%s" % (o["id"], o["sku"], o["target"]) for o in created)))

    say("[5] 清空库存流水（day14 基线要求 ledger 空；dev 库历史形态即「有订单/零流水」）")
    one("DELETE FROM inventory_logs;")
    n_logs = one("SELECT count(*) FROM inventory_logs;")
    checks.append(("ledger emptied (rows=%s)" % n_logs, n_logs == "0"))

    say("[6] 一致性核查")
    for sku in sorted({p["sku"] for p in PLAN}):
        ok, tals = identity_ok(sku)
        checks.append(("inventory identity sku%d (t=%d a=%d l=%d s=%d)" % (sku, *tals), ok))
        say("    sku%d total=%d available=%d locked=%d sold=%d %s"
            % ((sku,) + tals + ("OK" if ok else "IDENTITY BROKEN",)))
    locked_all = one("SELECT count(*) FROM inventories WHERE locked_stock <> 0;")
    checks.append(("locked=0 everywhere (rows=%s)" % locked_all, locked_all == "0"))
    if created:
        ids = ",".join(str(o["id"]) for o in created)
        pays = one("SELECT count(*) FROM payments WHERE order_id IN (%s);" % ids)
        checks.append(("payments rows for PAID orders (%s/%d)" % (pays, len(created)),
                       int(pays) == len(created)))

    # 状态文件：只在全部就绪时写（半途而废的夹具不许假装幂等）
    passed = sum(1 for _, ok in checks if ok)
    total = len(checks)
    if created and passed == total:
        json.dump({"created_at": one("SELECT to_char(now(),'YYYY-MM-DD HH24:MI:SS');"),
                   "orders": created,
                   "address_id": DEMO_ADDRESS_ID, "intruder_id": INTRUDER_ID},
                  open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        say("[5] 状态文件已写: %s" % os.path.basename(STATE))

    say("=" * 78)
    say("FIXTURE: %d / %d passed" % (passed, total))
    if passed != total:
        say("FAILED:")
        for name, ok in checks:
            if not ok:
                say("  [FAIL] %s" % name)
    flush()
    return 0 if (passed == total and created) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                                               # noqa: BLE001
        import traceback
        say("\nCRASH:\n" + traceback.format_exc())
        flush()
        raise
